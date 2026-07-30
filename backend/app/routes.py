from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.database import Conversation, FollowUpStage, SentMessageLog, TelegramAccount, Video, get_db
from app.mongo import get_fan_profile
from app.schemas import (
    ConversationOut,
    DashboardStats,
    FollowUpStageCreate,
    FollowUpStageOut,
    FollowUpStageUpdate,
    LoginRequest,
    LoginResponse,
    ReorderStages,
    TelegramAccountOut,
    TelegramAccountUpdate,
    TelegramSendCode,
    TelegramSignIn,
    TelegramTestSend,
    VideoOut,
    VideoUpdate,
)
from app.telegram_service import telegram_service
from app.s3_service import upload_video, delete_video, s3_ready

router = APIRouter(prefix="/api")


def require_admin(authorization: str | None = Header(default=None)) -> None:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = authorization.removeprefix("Bearer ").strip()
    if token != settings.admin_password:
        raise HTTPException(status_code=401, detail="Invalid token")


# --- Auth ---

@router.post("/auth/login", response_model=LoginResponse)
def login(body: LoginRequest) -> LoginResponse:
    if body.password != settings.admin_password:
        raise HTTPException(status_code=401, detail="Invalid password")
    return LoginResponse(token=settings.admin_password)


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


# --- Dashboard ---

@router.get("/stats", response_model=DashboardStats, dependencies=[Depends(require_admin)])
async def stats(db: Session = Depends(get_db)) -> DashboardStats:
    status = await telegram_service.status()
    active_stages = db.query(func.count(FollowUpStage.id)).filter(FollowUpStage.is_active.is_(True)).scalar() or 0
    tracked = db.query(func.count(Conversation.id)).scalar() or 0
    return DashboardStats(
        connected=status.get("connected", False),
        active_stages=active_stages,
        tracked_conversations=tracked,
        pending_follow_ups=telegram_service.count_pending(),
        sent_last_24h=telegram_service.sent_last_24h(),
    )


# --- Follow-Up Stages ---

@router.get("/stages", response_model=list[FollowUpStageOut], dependencies=[Depends(require_admin)])
def list_stages(account_id: int | None = None, db: Session = Depends(get_db)) -> list[FollowUpStage]:
    q = db.query(FollowUpStage)
    if account_id is not None:
        q = q.filter(FollowUpStage.account_id == account_id)
    return q.order_by(FollowUpStage.account_id, FollowUpStage.position).all()


@router.post("/stages", response_model=FollowUpStageOut, dependencies=[Depends(require_admin)])
def create_stage(body: FollowUpStageCreate, db: Session = Depends(get_db)) -> FollowUpStage:
    account = db.query(TelegramAccount).filter(TelegramAccount.id == body.account_id).one_or_none()
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")

    max_pos = (
        db.query(func.max(FollowUpStage.position))
        .filter(FollowUpStage.account_id == body.account_id)
        .scalar()
    )
    position = 0 if max_pos is None else max_pos + 1

    stage = FollowUpStage(
        account_id=body.account_id,
        position=position,
        delay_hours=body.delay_hours,
        system_prompt=body.system_prompt,
        is_active=body.is_active,
    )
    db.add(stage)
    db.commit()
    db.refresh(stage)
    return stage


@router.patch("/stages/{stage_id}", response_model=FollowUpStageOut, dependencies=[Depends(require_admin)])
def update_stage(stage_id: int, body: FollowUpStageUpdate, db: Session = Depends(get_db)) -> FollowUpStage:
    stage = db.query(FollowUpStage).filter(FollowUpStage.id == stage_id).one_or_none()
    if stage is None:
        raise HTTPException(status_code=404, detail="Stage not found")
    if body.delay_hours is not None:
        stage.delay_hours = body.delay_hours
    if body.system_prompt is not None:
        stage.system_prompt = body.system_prompt
    if body.is_active is not None:
        stage.is_active = body.is_active
    db.commit()
    db.refresh(stage)
    return stage


@router.delete("/stages/{stage_id}", dependencies=[Depends(require_admin)])
def delete_stage(stage_id: int, db: Session = Depends(get_db)) -> dict:
    stage = db.query(FollowUpStage).filter(FollowUpStage.id == stage_id).one_or_none()
    if stage is None:
        raise HTTPException(status_code=404, detail="Stage not found")
    account_id = stage.account_id
    db.delete(stage)
    db.commit()
    _reindex_stage_positions(db, account_id)
    return {"ok": True}


@router.put("/stages/reorder", response_model=list[FollowUpStageOut], dependencies=[Depends(require_admin)])
def reorder_stages(body: ReorderStages, db: Session = Depends(get_db)) -> list[FollowUpStage]:
    stages = {s.id: s for s in db.query(FollowUpStage).filter(FollowUpStage.id.in_(body.stage_ids)).all()}
    if set(body.stage_ids) != set(stages.keys()):
        raise HTTPException(status_code=400, detail="stage_ids must include every stage for this account")
    for position, stage_id in enumerate(body.stage_ids):
        stages[stage_id].position = position
    db.commit()
    account_id = next(iter(stages.values())).account_id if stages else None
    if account_id:
        return (
            db.query(FollowUpStage)
            .filter(FollowUpStage.account_id == account_id)
            .order_by(FollowUpStage.position)
            .all()
        )
    return []


def _reindex_stage_positions(db: Session, account_id: int) -> None:
    for position, stage in enumerate(
        db.query(FollowUpStage)
        .filter(FollowUpStage.account_id == account_id)
        .order_by(FollowUpStage.position)
        .all()
    ):
        stage.position = position
    db.commit()


# --- Videos ---

@router.get("/videos", response_model=list[VideoOut], dependencies=[Depends(require_admin)])
def list_videos(account_id: int | None = None, db: Session = Depends(get_db)) -> list[Video]:
    q = db.query(Video)
    if account_id is not None:
        q = q.filter(Video.account_id == account_id)
    return q.order_by(Video.created_at.desc()).all()


@router.post("/videos", response_model=VideoOut, dependencies=[Depends(require_admin)])
async def upload_video_endpoint(
    account_id: int = Form(...),
    tags: str = Form(""),
    description: str = Form(""),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> Video:
    if not s3_ready():
        raise HTTPException(status_code=400, detail="S3 not configured (missing AWS credentials)")

    account = db.query(TelegramAccount).filter(TelegramAccount.id == account_id).one_or_none()
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")

    file_bytes = await file.read()
    filename = file.filename or "video.mp4"
    s3_key = upload_video(account_id, filename, file_bytes)

    video = Video(
        account_id=account_id,
        s3_key=s3_key,
        filename=filename,
        tags=tags,
        description=description,
    )
    db.add(video)
    db.commit()
    db.refresh(video)
    return video


@router.patch("/videos/{video_id}", response_model=VideoOut, dependencies=[Depends(require_admin)])
def update_video(video_id: int, body: VideoUpdate, db: Session = Depends(get_db)) -> Video:
    video = db.query(Video).filter(Video.id == video_id).one_or_none()
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")
    if body.tags is not None:
        video.tags = body.tags
    if body.description is not None:
        video.description = body.description
    db.commit()
    db.refresh(video)
    return video


@router.delete("/videos/{video_id}", dependencies=[Depends(require_admin)])
def delete_video_endpoint(video_id: int, db: Session = Depends(get_db)) -> dict:
    video = db.query(Video).filter(Video.id == video_id).one_or_none()
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")
    delete_video(video.s3_key)
    db.delete(video)
    db.commit()
    return {"ok": True}


# --- Conversations ---

@router.get("/conversations", response_model=list[ConversationOut], dependencies=[Depends(require_admin)])
def list_conversations(account_id: int | None = None, db: Session = Depends(get_db)) -> list[Conversation]:
    q = db.query(Conversation)
    if account_id is not None:
        q = q.filter(Conversation.account_id == account_id)
    return q.order_by(Conversation.last_user_message_at.desc().nullslast()).limit(200).all()


@router.get("/conversations/{conversation_id}/fan-profile", dependencies=[Depends(require_admin)])
def get_conversation_fan_profile(conversation_id: int, db: Session = Depends(get_db)) -> dict:
    conversation = db.query(Conversation).filter(Conversation.id == conversation_id).one_or_none()
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    profile = get_fan_profile(conversation.account_id, conversation.telegram_user_id)
    return profile or {}


@router.post("/conversations/{conversation_id}/opt-out", dependencies=[Depends(require_admin)])
def opt_out_conversation(conversation_id: int, db: Session = Depends(get_db)) -> dict:
    conversation = db.query(Conversation).filter(Conversation.id == conversation_id).one_or_none()
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    conversation.opted_out = True
    db.commit()
    return {"ok": True}


# --- Telegram Accounts ---

@router.get("/telegram/accounts", response_model=list[TelegramAccountOut], dependencies=[Depends(require_admin)])
def list_telegram_accounts(db: Session = Depends(get_db)) -> list[TelegramAccount]:
    return db.query(TelegramAccount).order_by(TelegramAccount.created_at.desc()).all()


@router.get("/telegram/account", response_model=TelegramAccountOut | None, dependencies=[Depends(require_admin)])
def get_telegram_account(db: Session = Depends(get_db)) -> TelegramAccount | None:
    return db.query(TelegramAccount).order_by(TelegramAccount.id).first()


@router.patch("/telegram/accounts/{account_id}", response_model=TelegramAccountOut, dependencies=[Depends(require_admin)])
def update_telegram_account(account_id: int, body: TelegramAccountUpdate, db: Session = Depends(get_db)) -> TelegramAccount:
    account = db.query(TelegramAccount).filter(TelegramAccount.id == account_id).one_or_none()
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")
    if body.name is not None:
        account.name = body.name
    if body.personality is not None:
        account.personality = body.personality
    db.commit()
    db.refresh(account)
    return account


@router.delete("/telegram/accounts/{account_id}", dependencies=[Depends(require_admin)])
async def delete_telegram_account(account_id: int) -> dict:
    try:
        await telegram_service.remove_account(account_id)
        return {"ok": True}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/telegram/status", dependencies=[Depends(require_admin)])
async def telegram_status() -> dict:
    return await telegram_service.status()


@router.post("/telegram/send-code", dependencies=[Depends(require_admin)])
async def telegram_send_code(body: TelegramSendCode) -> dict:
    try:
        phone_code_hash = await telegram_service.send_code(body.phone)
        return {"phone_code_hash": phone_code_hash}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/telegram/sign-in", dependencies=[Depends(require_admin)])
async def telegram_sign_in(body: TelegramSignIn) -> dict:
    try:
        await telegram_service.sign_in(body.phone, body.code, body.phone_code_hash, body.password)
        return {"ok": True}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/telegram/run-now", dependencies=[Depends(require_admin)])
async def run_follow_ups_now() -> dict:
    sent = await telegram_service.run_follow_ups()
    return {"sent": sent}


@router.post("/telegram/test-send-first", dependencies=[Depends(require_admin)])
async def test_send_first_chat(body: TelegramTestSend = TelegramTestSend()) -> dict:
    try:
        return await telegram_service.send_test_to_first_chat(body.message)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
