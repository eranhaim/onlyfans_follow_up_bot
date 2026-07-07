import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy import func
from telethon import TelegramClient, events
from telethon.errors import SessionPasswordNeededError
from telethon.sessions import StringSession

from app.config import settings
from app.database import Conversation, FollowUpStep, SentMessageLog, SessionLocal, TelegramAccount

logger = logging.getLogger(__name__)


class TelegramService:
    def __init__(self) -> None:
        self._client: TelegramClient | None = None
        self._lock = asyncio.Lock()
        self._pending_logins: dict[str, dict] = {}

    def _api_ready(self) -> bool:
        return bool(settings.telegram_api_id and settings.telegram_api_hash)

    def _get_session_string(self, db) -> str | None:
        account = db.query(TelegramAccount).order_by(TelegramAccount.id).first()
        if account and account.session_string:
            return account.session_string
        return settings.telegram_session_string

    async def get_client(self) -> TelegramClient | None:
        if not self._api_ready():
            return None
        if self._client and self._client.is_connected():
            return self._client

        async with self._lock:
            if self._client and self._client.is_connected():
                return self._client

            db = SessionLocal()
            try:
                session_string = self._get_session_string(db)
            finally:
                db.close()

            if not session_string:
                return None

            client = TelegramClient(
                StringSession(session_string),
                settings.telegram_api_id,
                settings.telegram_api_hash,
            )
            await client.connect()
            if not await client.is_user_authorized():
                await client.disconnect()
                return None

            self._client = client
            self._register_handlers(client)
            return client

    def _register_handlers(self, client: TelegramClient) -> None:
        @client.on(events.NewMessage(incoming=True))
        async def on_incoming(event: events.NewMessage.Event) -> None:
            if not event.is_private:
                return
            if event.out:
                return

            sender = await event.get_sender()
            if sender is None or getattr(sender, "bot", False):
                return

            user_id = sender.id
            display_name = " ".join(
                part for part in [getattr(sender, "first_name", None), getattr(sender, "last_name", None)] if part
            ) or getattr(sender, "username", None)

            db = SessionLocal()
            try:
                account = db.query(TelegramAccount).order_by(TelegramAccount.id).first()
                if account is None:
                    account = TelegramAccount(name="Model", is_connected=True)
                    db.add(account)
                    db.flush()

                conversation = (
                    db.query(Conversation)
                    .filter_by(account_id=account.id, telegram_user_id=user_id)
                    .one_or_none()
                )
                now = datetime.utcnow()
                if conversation is None:
                    conversation = Conversation(
                        account_id=account.id,
                        telegram_user_id=user_id,
                        display_name=display_name,
                        last_user_message_at=now,
                        steps_sent=0,
                    )
                    db.add(conversation)
                else:
                    conversation.last_user_message_at = now
                    conversation.display_name = display_name or conversation.display_name
                    conversation.steps_sent = 0
                    conversation.last_follow_up_at = None

                text = (event.message.message or "").strip().lower()
                if text in {"stop", "unsubscribe", "/stop"}:
                    conversation.opted_out = True

                db.commit()
            finally:
                db.close()

    async def disconnect(self) -> None:
        if self._client:
            await self._client.disconnect()
            self._client = None

    async def send_code(self, phone: str) -> str:
        if not self._api_ready():
            raise ValueError("Set TELEGRAM_API_ID and TELEGRAM_API_HASH in .env")

        client = TelegramClient(StringSession(), settings.telegram_api_id, settings.telegram_api_hash)
        await client.connect()
        try:
            result = await client.send_code_request(phone)
            self._pending_logins[phone] = {"client": client, "phone_code_hash": result.phone_code_hash}
            return result.phone_code_hash
        except Exception:
            await client.disconnect()
            raise

    async def sign_in(self, phone: str, code: str, phone_code_hash: str, password: str | None = None) -> str:
        pending = self._pending_logins.get(phone)
        if pending is None:
            raise ValueError("No pending login for this phone. Request a code first.")

        client: TelegramClient = pending["client"]
        try:
            await client.sign_in(phone=phone, code=code, phone_code_hash=phone_code_hash)
        except SessionPasswordNeededError:
            if not password:
                raise ValueError("Two-factor password required")
            await client.sign_in(password=password)

        session_string = client.session.save()
        await client.disconnect()
        self._pending_logins.pop(phone, None)

        db = SessionLocal()
        try:
            account = db.query(TelegramAccount).filter(TelegramAccount.phone == phone).one_or_none()
            if account is None:
                account = TelegramAccount(name="Model", phone=phone)
                db.add(account)
            account.phone = phone
            account.session_string = session_string
            account.is_connected = True
            db.commit()
        finally:
            db.close()

        self._client = None
        return session_string

    async def status(self) -> dict:
        client = await self.get_client()
        if client is None:
            return {"connected": False}
        me = await client.get_me()
        return {
            "connected": True,
            "user_id": me.id,
            "username": me.username,
            "first_name": me.first_name,
        }

    async def send_test_to_first_chat(self, message: str = " test") -> dict:
        client = await self.get_client()
        if client is None:
            raise ValueError("Telegram not connected")

        async for dialog in client.iter_dialogs(limit=1):
            entity = dialog.entity
            sent = await client.send_message(entity, message)
            name = dialog.name or dialog.title or str(dialog.id)
            return {
                "ok": True,
                "chat_id": dialog.id,
                "chat_name": name,
                "message": message,
                "message_id": sent.id,
            }

        raise ValueError("No chats found on this account")

    async def remove_account(self, account_id: int) -> None:
        db = SessionLocal()
        try:
            account = db.query(TelegramAccount).filter(TelegramAccount.id == account_id).one_or_none()
            if account is None:
                raise ValueError("Account not found")

            conversation_ids = [
                row[0]
                for row in db.query(Conversation.id).filter(Conversation.account_id == account_id).all()
            ]
            if conversation_ids:
                db.query(SentMessageLog).filter(SentMessageLog.conversation_id.in_(conversation_ids)).delete(
                    synchronize_session=False
                )
                db.query(Conversation).filter(Conversation.account_id == account_id).delete(
                    synchronize_session=False
                )

            db.delete(account)
            db.commit()
        finally:
            db.close()

        await self.disconnect()

    async def run_follow_ups(self) -> int:
        client = await self.get_client()
        if client is None:
            return 0

        db = SessionLocal()
        sent_count = 0
        try:
            steps = (
                db.query(FollowUpStep)
                .filter(FollowUpStep.is_active.is_(True))
                .order_by(FollowUpStep.position)
                .all()
            )
            if not steps:
                return 0

            account = db.query(TelegramAccount).order_by(TelegramAccount.id).first()
            if account is None:
                return 0

            now = datetime.utcnow()
            conversations = (
                db.query(Conversation)
                .filter(
                    Conversation.account_id == account.id,
                    Conversation.opted_out.is_(False),
                    Conversation.last_user_message_at.isnot(None),
                )
                .all()
            )

            for conversation in conversations:
                if conversation.steps_sent >= len(steps):
                    continue

                step = steps[conversation.steps_sent]
                if conversation.last_user_message_at is None:
                    continue

                due_at = conversation.last_user_message_at + timedelta(hours=step.delay_hours)
                if now < due_at:
                    continue

                try:
                    await client.send_message(conversation.telegram_user_id, step.message_text)
                    conversation.steps_sent += 1
                    conversation.last_follow_up_at = now
                    db.add(
                        SentMessageLog(
                            conversation_id=conversation.id,
                            step_id=step.id,
                            message_text=step.message_text,
                            success=True,
                        )
                    )
                    sent_count += 1
                except Exception as exc:
                    logger.exception("Failed to send follow-up to %s", conversation.telegram_user_id)
                    db.add(
                        SentMessageLog(
                            conversation_id=conversation.id,
                            step_id=step.id,
                            message_text=step.message_text,
                            success=False,
                            error=str(exc),
                        )
                    )

            db.commit()
        finally:
            db.close()

        return sent_count

    def count_pending(self) -> int:
        db = SessionLocal()
        try:
            steps = (
                db.query(FollowUpStep)
                .filter(FollowUpStep.is_active.is_(True))
                .order_by(FollowUpStep.position)
                .all()
            )
            if not steps:
                return 0

            now = datetime.utcnow()
            pending = 0
            conversations = db.query(Conversation).filter(Conversation.opted_out.is_(False)).all()
            for conversation in conversations:
                if conversation.steps_sent >= len(steps) or conversation.last_user_message_at is None:
                    continue
                step = steps[conversation.steps_sent]
                due_at = conversation.last_user_message_at + timedelta(hours=step.delay_hours)
                if now >= due_at:
                    pending += 1
            return pending
        finally:
            db.close()

    def sent_last_24h(self) -> int:
        db = SessionLocal()
        try:
            since = datetime.utcnow() - timedelta(hours=24)
            return (
                db.query(func.count(SentMessageLog.id))
                .filter(SentMessageLog.sent_at >= since, SentMessageLog.success.is_(True))
                .scalar()
                or 0
            )
        finally:
            db.close()


telegram_service = TelegramService()
