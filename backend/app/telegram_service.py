import asyncio
import logging
import os
from datetime import datetime, timedelta

from sqlalchemy import func
from telethon import TelegramClient, events
from telethon.errors import SessionPasswordNeededError
from telethon.sessions import StringSession

from app.config import settings
from app.database import (
    Conversation,
    FollowUpStage,
    SentMessageLog,
    SessionLocal,
    TelegramAccount,
    Video,
)
from app.mongo import store_message, get_chat_history, delete_chat_history, get_fan_profile, save_fan_profile
from app.llm_service import generate_follow_up, analyze_fan, llm_ready
from app.s3_service import download_video, s3_ready

logger = logging.getLogger(__name__)


class TelegramService:
    def __init__(self) -> None:
        self._clients: dict[int, TelegramClient] = {}
        self._lock = asyncio.Lock()
        self._pending_logins: dict[str, dict] = {}

    def _api_ready(self) -> bool:
        return bool(settings.telegram_api_id and settings.telegram_api_hash)

    async def get_client_for_account(self, account: TelegramAccount) -> TelegramClient | None:
        if not self._api_ready():
            return None
        if not account.session_string:
            return None

        if account.id in self._clients:
            client = self._clients[account.id]
            if client.is_connected():
                return client

        async with self._lock:
            if account.id in self._clients and self._clients[account.id].is_connected():
                return self._clients[account.id]

            client = TelegramClient(
                StringSession(account.session_string),
                settings.telegram_api_id,
                settings.telegram_api_hash,
            )
            await client.connect()
            if not await client.is_user_authorized():
                await client.disconnect()
                return None

            self._clients[account.id] = client
            self._register_handlers(client, account.id)
            return client

    async def connect_all(self) -> None:
        """Connect all stored accounts on startup."""
        if not self._api_ready():
            return
        db = SessionLocal()
        try:
            accounts = db.query(TelegramAccount).filter(
                TelegramAccount.session_string.isnot(None),
                TelegramAccount.is_connected.is_(True),
            ).all()
            for account in accounts:
                try:
                    await self.get_client_for_account(account)
                    logger.info("Connected account %s (%s)", account.id, account.name)
                except Exception:
                    logger.exception("Failed to connect account %s", account.id)
        finally:
            db.close()

    def _register_handlers(self, client: TelegramClient, account_id: int) -> None:
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

            text = (event.message.message or "").strip()

            # Store in MongoDB
            store_message(account_id, user_id, "user", text)

            # Analyze fan profile in background (non-blocking)
            if llm_ready() and text:
                def _update_profile(acc_id: int, u_id: int) -> None:
                    try:
                        history = get_chat_history(acc_id, u_id)
                        existing = get_fan_profile(acc_id, u_id)
                        profile = analyze_fan(history, existing)
                        if profile:
                            save_fan_profile(acc_id, u_id, profile)
                    except Exception:
                        logger.exception("Failed to analyze fan profile for user %s", u_id)

                asyncio.get_event_loop().run_in_executor(None, _update_profile, account_id, user_id)

            db = SessionLocal()
            try:
                conversation = (
                    db.query(Conversation)
                    .filter_by(account_id=account_id, telegram_user_id=user_id)
                    .one_or_none()
                )
                now = datetime.utcnow()
                if conversation is None:
                    conversation = Conversation(
                        account_id=account_id,
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

                if text.lower() in {"stop", "unsubscribe", "/stop"}:
                    conversation.opted_out = True

                db.commit()
            finally:
                db.close()

    async def disconnect(self) -> None:
        for account_id, client in list(self._clients.items()):
            try:
                await client.disconnect()
            except Exception:
                pass
        self._clients.clear()

    async def disconnect_account(self, account_id: int) -> None:
        client = self._clients.pop(account_id, None)
        if client:
            try:
                await client.disconnect()
            except Exception:
                pass

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
            db.refresh(account)
            account_id = account.id
        finally:
            db.close()

        # Reconnect this account
        db = SessionLocal()
        try:
            account = db.query(TelegramAccount).get(account_id)
            if account:
                await self.get_client_for_account(account)
        finally:
            db.close()

        return session_string

    async def status(self) -> dict:
        db = SessionLocal()
        try:
            account = db.query(TelegramAccount).filter(
                TelegramAccount.is_connected.is_(True)
            ).order_by(TelegramAccount.id).first()
            if account is None:
                return {"connected": False}

            client = await self.get_client_for_account(account)
            if client is None:
                return {"connected": False}

            me = await client.get_me()
            return {
                "connected": True,
                "user_id": me.id,
                "username": me.username,
                "first_name": me.first_name,
            }
        finally:
            db.close()

    async def send_test_to_first_chat(self, message: str = " test") -> dict:
        db = SessionLocal()
        try:
            account = db.query(TelegramAccount).filter(
                TelegramAccount.is_connected.is_(True)
            ).order_by(TelegramAccount.id).first()
            if account is None:
                raise ValueError("No connected Telegram account")
            client = await self.get_client_for_account(account)
        finally:
            db.close()

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
        await self.disconnect_account(account_id)

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

            db.query(FollowUpStage).filter(FollowUpStage.account_id == account_id).delete(
                synchronize_session=False
            )
            db.query(Video).filter(Video.account_id == account_id).delete(
                synchronize_session=False
            )
            db.delete(account)
            db.commit()
        finally:
            db.close()

        delete_chat_history(account_id)

    async def run_follow_ups(self) -> int:
        if not self._api_ready():
            return 0

        db = SessionLocal()
        sent_count = 0
        try:
            accounts = db.query(TelegramAccount).filter(
                TelegramAccount.is_connected.is_(True),
                TelegramAccount.session_string.isnot(None),
            ).all()

            now = datetime.utcnow()

            for account in accounts:
                client = await self.get_client_for_account(account)
                if client is None:
                    continue

                stages = (
                    db.query(FollowUpStage)
                    .filter(
                        FollowUpStage.account_id == account.id,
                        FollowUpStage.is_active.is_(True),
                    )
                    .order_by(FollowUpStage.position)
                    .all()
                )
                if not stages:
                    continue

                conversations = (
                    db.query(Conversation)
                    .filter(
                        Conversation.account_id == account.id,
                        Conversation.opted_out.is_(False),
                        Conversation.last_user_message_at.isnot(None),
                    )
                    .all()
                )

                videos = db.query(Video).filter(Video.account_id == account.id).all()
                video_list = [
                    {"id": v.id, "tags": v.tags, "description": v.description, "filename": v.filename}
                    for v in videos
                ] if videos else None

                for conversation in conversations:
                    if conversation.steps_sent >= len(stages):
                        continue

                    stage = stages[conversation.steps_sent]

                    # Timing: step 0 from last_user_message, step 1+ from last_follow_up
                    if conversation.steps_sent == 0:
                        reference_time = conversation.last_user_message_at
                    else:
                        reference_time = conversation.last_follow_up_at or conversation.last_user_message_at

                    if reference_time is None:
                        continue

                    due_at = reference_time + timedelta(hours=stage.delay_hours)
                    if now < due_at:
                        continue

                    # Generate message with LLM or fallback
                    message_text = None
                    video_id = None

                    if llm_ready() and stage.system_prompt.strip():
                        try:
                            history = get_chat_history(account.id, conversation.telegram_user_id)
                            full_prompt = stage.system_prompt
                            if account.personality and account.personality.strip():
                                full_prompt = account.personality.strip() + "\n\n" + full_prompt
                            fan_profile = get_fan_profile(account.id, conversation.telegram_user_id)
                            result = generate_follow_up(
                                system_prompt=full_prompt,
                                chat_history=history,
                                available_videos=video_list,
                                fan_profile=fan_profile,
                                stage_index=conversation.steps_sent,
                            )
                            message_text = result["message"]
                            video_id = result.get("video_id")
                        except Exception:
                            logger.exception(
                                "LLM generation failed for conversation %s, stage %s",
                                conversation.id, stage.id,
                            )

                    if not message_text:
                        message_text = f"Hey! 💕"

                    # Send message
                    try:
                        await client.send_message(conversation.telegram_user_id, message_text)

                        # Send video if selected
                        if video_id and s3_ready():
                            video_obj = db.query(Video).filter(Video.id == video_id).one_or_none()
                            if video_obj:
                                try:
                                    tmp_path = download_video(video_obj.s3_key)
                                    await client.send_file(
                                        conversation.telegram_user_id,
                                        tmp_path,
                                        caption="",
                                    )
                                    os.unlink(tmp_path)
                                except Exception:
                                    logger.exception("Failed to send video %s", video_id)

                        # Store assistant message in MongoDB
                        store_message(account.id, conversation.telegram_user_id, "assistant", message_text)

                        conversation.steps_sent += 1
                        conversation.last_follow_up_at = now
                        db.add(SentMessageLog(
                            conversation_id=conversation.id,
                            stage_id=stage.id,
                            video_id=video_id,
                            message_text=message_text,
                            success=True,
                        ))
                        sent_count += 1
                    except Exception as exc:
                        logger.exception("Failed to send follow-up to %s", conversation.telegram_user_id)
                        db.add(SentMessageLog(
                            conversation_id=conversation.id,
                            stage_id=stage.id,
                            message_text=message_text,
                            success=False,
                            error=str(exc),
                        ))

            db.commit()
        finally:
            db.close()

        return sent_count

    def count_pending(self) -> int:
        db = SessionLocal()
        try:
            now = datetime.utcnow()
            pending = 0

            accounts = db.query(TelegramAccount).filter(
                TelegramAccount.is_connected.is_(True),
            ).all()

            for account in accounts:
                stages = (
                    db.query(FollowUpStage)
                    .filter(
                        FollowUpStage.account_id == account.id,
                        FollowUpStage.is_active.is_(True),
                    )
                    .order_by(FollowUpStage.position)
                    .all()
                )
                if not stages:
                    continue

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
                    if conversation.steps_sent >= len(stages):
                        continue
                    stage = stages[conversation.steps_sent]
                    if conversation.steps_sent == 0:
                        ref = conversation.last_user_message_at
                    else:
                        ref = conversation.last_follow_up_at or conversation.last_user_message_at
                    if ref is None:
                        continue
                    due_at = ref + timedelta(hours=stage.delay_hours)
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
