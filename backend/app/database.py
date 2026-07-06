from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


class TelegramAccount(Base):
    __tablename__ = "telegram_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), default="Model")
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    session_string: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_connected: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    conversations: Mapped[list["Conversation"]] = relationship(back_populates="account")


class FollowUpStep(Base):
    __tablename__ = "follow_up_steps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    position: Mapped[int] = mapped_column(Integer, index=True)
    delay_hours: Mapped[float] = mapped_column(Float)
    message_text: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("telegram_accounts.id"), index=True)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    display_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    last_user_message_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    steps_sent: Mapped[int] = mapped_column(Integer, default=0)
    last_follow_up_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    opted_out: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    account: Mapped["TelegramAccount"] = relationship(back_populates="conversations")


class SentMessageLog(Base):
    __tablename__ = "sent_message_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"), index=True)
    step_id: Mapped[int | None] = mapped_column(ForeignKey("follow_up_steps.id"), nullable=True)
    message_text: Mapped[str] = mapped_column(Text)
    sent_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
