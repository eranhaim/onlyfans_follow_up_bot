from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import Conversation, FollowUpStep, TelegramAccount, get_db
from app.schemas import (
    ConversationOut,
    DashboardStats,
    FollowUpStepCreate,
    FollowUpStepOut,
    FollowUpStepUpdate,
    LoginRequest,
    LoginResponse,
    ReorderSteps,
    TelegramAccountOut,
    TelegramSendCode,
    TelegramSignIn,
)
from app.config import settings
from app.telegram_service import telegram_service

router = APIRouter(prefix="/api")


def require_admin(authorization: str | None = Header(default=None)) -> None:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = authorization.removeprefix("Bearer ").strip()
    if token != settings.admin_password:
        raise HTTPException(status_code=401, detail="Invalid token")


@router.post("/auth/login", response_model=LoginResponse)
def login(body: LoginRequest) -> LoginResponse:
    if body.password != settings.admin_password:
        raise HTTPException(status_code=401, detail="Invalid password")
    return LoginResponse(token=settings.admin_password)


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/stats", response_model=DashboardStats, dependencies=[Depends(require_admin)])
async def stats(db: Session = Depends(get_db)) -> DashboardStats:
    status = await telegram_service.status()
    active_steps = db.query(func.count(FollowUpStep.id)).filter(FollowUpStep.is_active.is_(True)).scalar() or 0
    tracked = db.query(func.count(Conversation.id)).scalar() or 0
    return DashboardStats(
        connected=status.get("connected", False),
        active_steps=active_steps,
        tracked_conversations=tracked,
        pending_follow_ups=telegram_service.count_pending(),
        sent_last_24h=telegram_service.sent_last_24h(),
    )


@router.get("/steps", response_model=list[FollowUpStepOut], dependencies=[Depends(require_admin)])
def list_steps(db: Session = Depends(get_db)) -> list[FollowUpStep]:
    return db.query(FollowUpStep).order_by(FollowUpStep.position).all()


@router.post("/steps", response_model=FollowUpStepOut, dependencies=[Depends(require_admin)])
def create_step(body: FollowUpStepCreate, db: Session = Depends(get_db)) -> FollowUpStep:
    max_pos = db.query(func.max(FollowUpStep.position)).scalar()
    position = 0 if max_pos is None else max_pos + 1
    step = FollowUpStep(
        position=position,
        delay_hours=body.delay_hours,
        message_text=body.message_text,
        is_active=body.is_active,
    )
    db.add(step)
    db.commit()
    db.refresh(step)
    return step


@router.patch("/steps/{step_id}", response_model=FollowUpStepOut, dependencies=[Depends(require_admin)])
def update_step(step_id: int, body: FollowUpStepUpdate, db: Session = Depends(get_db)) -> FollowUpStep:
    step = db.query(FollowUpStep).filter(FollowUpStep.id == step_id).one_or_none()
    if step is None:
        raise HTTPException(status_code=404, detail="Step not found")
    if body.delay_hours is not None:
        step.delay_hours = body.delay_hours
    if body.message_text is not None:
        step.message_text = body.message_text
    if body.is_active is not None:
        step.is_active = body.is_active
    db.commit()
    db.refresh(step)
    return step


@router.delete("/steps/{step_id}", dependencies=[Depends(require_admin)])
def delete_step(step_id: int, db: Session = Depends(get_db)) -> dict:
    step = db.query(FollowUpStep).filter(FollowUpStep.id == step_id).one_or_none()
    if step is None:
        raise HTTPException(status_code=404, detail="Step not found")
    db.delete(step)
    db.commit()
    _reindex_positions(db)
    return {"ok": True}


@router.put("/steps/reorder", response_model=list[FollowUpStepOut], dependencies=[Depends(require_admin)])
def reorder_steps(body: ReorderSteps, db: Session = Depends(get_db)) -> list[FollowUpStep]:
    steps = {s.id: s for s in db.query(FollowUpStep).all()}
    if set(body.step_ids) != set(steps.keys()):
        raise HTTPException(status_code=400, detail="step_ids must include every step exactly once")
    for position, step_id in enumerate(body.step_ids):
        steps[step_id].position = position
    db.commit()
    return db.query(FollowUpStep).order_by(FollowUpStep.position).all()


def _reindex_positions(db: Session) -> None:
    for position, step in enumerate(db.query(FollowUpStep).order_by(FollowUpStep.position).all()):
        step.position = position
    db.commit()


@router.get("/conversations", response_model=list[ConversationOut], dependencies=[Depends(require_admin)])
def list_conversations(db: Session = Depends(get_db)) -> list[Conversation]:
    return (
        db.query(Conversation)
        .order_by(Conversation.last_user_message_at.desc().nullslast())
        .limit(200)
        .all()
    )


@router.post("/conversations/{conversation_id}/opt-out", dependencies=[Depends(require_admin)])
def opt_out_conversation(conversation_id: int, db: Session = Depends(get_db)) -> dict:
    conversation = db.query(Conversation).filter(Conversation.id == conversation_id).one_or_none()
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    conversation.opted_out = True
    db.commit()
    return {"ok": True}


@router.get("/telegram/account", response_model=TelegramAccountOut | None, dependencies=[Depends(require_admin)])
def get_telegram_account(db: Session = Depends(get_db)) -> TelegramAccount | None:
    return db.query(TelegramAccount).order_by(TelegramAccount.id).first()


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
