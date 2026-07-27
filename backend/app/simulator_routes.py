from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta
from typing import Optional
import threading
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db, FollowUpStage, Video, TelegramAccount
from app.llm_service import generate_follow_up, llm_ready
from app.routes import require_admin

router = APIRouter(prefix="/api/simulator", tags=["simulator"])

SESSION_TTL_HOURS = 2


@dataclass
class SimMessage:
    role: str                       # "user" | "bot"
    content: str
    stage_position: Optional[int]   # None for user messages
    video_id: Optional[int]
    video_filename: Optional[str]
    sim_time: str                   # ISO datetime string


@dataclass
class SimSession:
    session_id: str
    account_id: int
    stages: list                    # snapshot of active FollowUpStage dicts
    videos: list                    # snapshot of Video dicts
    messages: list                  # list[SimMessage]
    steps_sent: int
    sim_now: datetime
    last_user_message_at: Optional[datetime]
    last_follow_up_at: Optional[datetime]
    created_at: datetime = field(default_factory=datetime.utcnow)


_sessions: dict[str, SimSession] = {}
_sessions_lock = threading.Lock()


def _cleanup(sessions: dict) -> None:
    cutoff = datetime.utcnow() - timedelta(hours=SESSION_TTL_HOURS)
    expired = [sid for sid, s in sessions.items() if s.created_at < cutoff]
    for sid in expired:
        del sessions[sid]


def _tick(session: SimSession) -> None:
    """Fire all follow-up stages that are due at or before session.sim_now."""
    active = [s for s in session.stages if s["is_active"]]
    while session.steps_sent < len(active):
        stage = active[session.steps_sent]
        ref = session.last_user_message_at
        if session.steps_sent > 0:
            ref = session.last_follow_up_at or session.last_user_message_at
        if ref is None:
            break
        due_at = ref + timedelta(hours=stage["delay_hours"])
        if session.sim_now < due_at:
            break
        history = [{"role": m.role, "content": m.content} for m in session.messages]
        if llm_ready():
            try:
                result = generate_follow_up(
                    system_prompt=stage["system_prompt"],
                    chat_history=history,
                    available_videos=session.videos if session.videos else None,
                )
            except Exception:
                result = {"message": "Hey! 💕", "video_id": None}
        else:
            result = {"message": "Hey! 💕", "video_id": None}
        vid_filename = None
        if result.get("video_id"):
            vid = next((v for v in session.videos if v["id"] == result["video_id"]), None)
            vid_filename = vid["filename"] if vid else None
        session.messages.append(SimMessage(
            role="bot",
            content=result["message"],
            stage_position=stage["position"],
            video_id=result.get("video_id"),
            video_filename=vid_filename,
            sim_time=due_at.isoformat(),
        ))
        session.steps_sent += 1
        session.last_follow_up_at = due_at


def _to_dict(session: SimSession) -> dict:
    active = [s for s in session.stages if s["is_active"]]
    next_stage = active[session.steps_sent] if session.steps_sent < len(active) else None
    next_due = None
    if next_stage:
        ref = session.last_user_message_at
        if session.steps_sent > 0:
            ref = session.last_follow_up_at or session.last_user_message_at
        if ref:
            next_due = ref + timedelta(hours=next_stage["delay_hours"])
    hours_until = (next_due - session.sim_now).total_seconds() / 3600 if next_due else None
    return {
        "session_id": session.session_id,
        "account_id": session.account_id,
        "stages": session.stages,
        "videos": session.videos,
        "messages": [asdict(m) for m in session.messages],
        "steps_sent": session.steps_sent,
        "sim_now": session.sim_now.isoformat(),
        "last_user_message_at": session.last_user_message_at.isoformat() if session.last_user_message_at else None,
        "last_follow_up_at": session.last_follow_up_at.isoformat() if session.last_follow_up_at else None,
        "next_stage_index": session.steps_sent if next_stage else None,
        "next_follow_up_due_at": next_due.isoformat() if next_due else None,
        "hours_until_next": round(hours_until, 2) if hours_until is not None else None,
        "sequence_complete": session.steps_sent >= len(active),
    }


class StartBody(BaseModel):
    account_id: int


class MessageBody(BaseModel):
    content: str


class AdvanceBody(BaseModel):
    hours: float


@router.post("/start")
def start_session(body: StartBody, db: Session = Depends(get_db), _: str = Depends(require_admin)):
    account = db.query(TelegramAccount).filter(TelegramAccount.id == body.account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    stages_q = (
        db.query(FollowUpStage)
        .filter(FollowUpStage.account_id == body.account_id, FollowUpStage.is_active == True)  # noqa: E712
        .order_by(FollowUpStage.position)
        .all()
    )
    if not stages_q:
        raise HTTPException(status_code=400, detail="No active stages for this account")
    videos_q = db.query(Video).filter(Video.account_id == body.account_id).all()
    stages = [
        {
            "id": s.id,
            "position": s.position,
            "delay_hours": s.delay_hours,
            "system_prompt": s.system_prompt,
            "is_active": s.is_active,
        }
        for s in stages_q
    ]
    videos = [
        {"id": v.id, "filename": v.filename, "description": v.description, "tags": v.tags}
        for v in videos_q
    ]
    session = SimSession(
        session_id=str(uuid.uuid4()),
        account_id=body.account_id,
        stages=stages,
        videos=videos,
        messages=[],
        steps_sent=0,
        sim_now=datetime.utcnow(),
        last_user_message_at=None,
        last_follow_up_at=None,
    )
    with _sessions_lock:
        _cleanup(_sessions)
        _sessions[session.session_id] = session
    return _to_dict(session)


@router.get("/{session_id}")
def get_session(session_id: str, _: str = Depends(require_admin)):
    with _sessions_lock:
        session = _sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return _to_dict(session)


@router.post("/{session_id}/message")
def send_message(session_id: str, body: MessageBody, _: str = Depends(require_admin)):
    with _sessions_lock:
        session = _sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    session.messages.append(SimMessage(
        role="user",
        content=body.content,
        stage_position=None,
        video_id=None,
        video_filename=None,
        sim_time=session.sim_now.isoformat(),
    ))
    session.last_user_message_at = session.sim_now
    session.steps_sent = 0
    session.last_follow_up_at = None
    return _to_dict(session)


@router.post("/{session_id}/advance")
def advance_time(session_id: str, body: AdvanceBody, _: str = Depends(require_admin)):
    with _sessions_lock:
        session = _sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    session.sim_now += timedelta(hours=body.hours)
    _tick(session)
    return _to_dict(session)


@router.delete("/{session_id}")
def delete_session(session_id: str, _: str = Depends(require_admin)):
    with _sessions_lock:
        _sessions.pop(session_id, None)
    return {"ok": True}
