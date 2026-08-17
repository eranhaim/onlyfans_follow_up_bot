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
    ChannelAccount,
    Conversation,
    FollowUpStage,
    SentMessageLog,
    SessionLocal,
    TelegramAccount,
    TelegramChannel,
    Video,
)
from app.mongo import store_message, get_chat_history, delete_chat_history, get_fan_profile, save_fan_profile, get_chat_collection
from app.llm_service import generate_follow_up, run_follow_up_graph, analyze_fan, llm_ready
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

        # Import existing chat history in background
        asyncio.ensure_future(self._import_history_background(account_id))

        return session_string

    async def _import_history_background(self, account_id: int) -> None:
        try:
            result = await self.import_chat_history(account_id)
            logger.info("Background import done for account %s: %s", account_id, result)
        except Exception:
            logger.exception("Background import failed for account %s", account_id)

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

    # --- Channel Account management ---

    async def _get_channel_client(self, channel_account: ChannelAccount) -> TelegramClient | None:
        """Get or create a Telethon client for a ChannelAccount."""
        if not self._api_ready():
            return None
        if not channel_account.session_string:
            return None

        key = f"ch_{channel_account.id}"
        if key in self._clients:
            client = self._clients[key]
            if client.is_connected():
                return client

        async with self._lock:
            if key in self._clients and self._clients[key].is_connected():
                return self._clients[key]

            client = TelegramClient(
                StringSession(channel_account.session_string),
                settings.telegram_api_id,
                settings.telegram_api_hash,
            )
            await client.connect()
            if not await client.is_user_authorized():
                await client.disconnect()
                return None

            self._clients[key] = client
            return client

    async def channel_send_code(self, phone: str) -> str:
        if not self._api_ready():
            raise ValueError("Set TELEGRAM_API_ID and TELEGRAM_API_HASH in .env")
        client = TelegramClient(StringSession(), settings.telegram_api_id, settings.telegram_api_hash)
        await client.connect()
        try:
            result = await client.send_code_request(phone)
            self._pending_logins[f"ch_{phone}"] = {"client": client, "phone_code_hash": result.phone_code_hash}
            return result.phone_code_hash
        except Exception:
            await client.disconnect()
            raise

    async def channel_sign_in(self, phone: str, code: str, phone_code_hash: str, password: str | None = None) -> None:
        pending = self._pending_logins.get(f"ch_{phone}")
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
        self._pending_logins.pop(f"ch_{phone}", None)

        db = SessionLocal()
        try:
            account = db.query(ChannelAccount).filter(ChannelAccount.phone == phone).one_or_none()
            if account is None:
                account = ChannelAccount(name="Channel Manager", phone=phone)
                db.add(account)
            account.session_string = session_string
            account.is_connected = True
            db.commit()
            db.refresh(account)
            ca_id = account.id
        finally:
            db.close()

        # Reconnect
        db = SessionLocal()
        try:
            account = db.query(ChannelAccount).get(ca_id)
            if account:
                await self._get_channel_client(account)
        finally:
            db.close()

    async def remove_channel_account(self, channel_account_id: int) -> None:
        key = f"ch_{channel_account_id}"
        client = self._clients.pop(key, None)
        if client:
            try:
                await client.disconnect()
            except Exception:
                pass

        db = SessionLocal()
        try:
            account = db.query(ChannelAccount).filter(ChannelAccount.id == channel_account_id).one_or_none()
            if account is None:
                raise ValueError("Channel account not found")
            db.query(TelegramChannel).filter(TelegramChannel.channel_account_id == channel_account_id).delete(
                synchronize_session=False
            )
            db.delete(account)
            db.commit()
        finally:
            db.close()

    async def sync_channels(self, channel_account_id: int) -> list[dict]:
        """Fetch channels/groups the channel account administers and sync to DB."""
        db = SessionLocal()
        try:
            account = db.query(ChannelAccount).filter(ChannelAccount.id == channel_account_id).one_or_none()
            if account is None:
                raise ValueError("Channel account not found")

            client = await self._get_channel_client(account)
            if client is None:
                raise ValueError("Channel account not connected")

            from telethon.tl.types import Channel

            channels_found = []
            async for dialog in client.iter_dialogs():
                entity = dialog.entity
                if not isinstance(entity, Channel):
                    continue
                if not (entity.creator or entity.admin_rights):
                    continue

                full = await client(
                    __import__("telethon.tl.functions.channels", fromlist=["GetFullChannelRequest"]).GetFullChannelRequest(entity)
                )
                participants_count = full.full_chat.participants_count or 0

                existing = db.query(TelegramChannel).filter(
                    TelegramChannel.channel_id == entity.id
                ).one_or_none()

                if existing:
                    existing.title = entity.title or existing.title
                    existing.username = entity.username
                    existing.subscribers_count = participants_count
                    existing.channel_account_id = channel_account_id
                else:
                    existing = TelegramChannel(
                        channel_account_id=channel_account_id,
                        channel_id=entity.id,
                        title=entity.title or "Unknown",
                        username=entity.username,
                        subscribers_count=participants_count,
                    )
                    db.add(existing)

                channels_found.append({
                    "channel_id": entity.id,
                    "title": entity.title,
                    "username": entity.username,
                    "subscribers_count": participants_count,
                })

            db.commit()
            return channels_found
        finally:
            db.close()

    async def get_channel_subscribers(self, channel_db_id: int) -> list[dict]:
        """Fetch subscriber list for a channel."""
        db = SessionLocal()
        try:
            channel = db.query(TelegramChannel).filter(TelegramChannel.id == channel_db_id).one_or_none()
            if channel is None:
                raise ValueError("Channel not found")

            account = db.query(ChannelAccount).filter(ChannelAccount.id == channel.channel_account_id).one_or_none()
            if account is None:
                raise ValueError("Channel account not found")

            client = await self._get_channel_client(account)
            if client is None:
                raise ValueError("Channel account not connected")

            from telethon.tl.functions.channels import GetParticipantsRequest
            from telethon.tl.types import ChannelParticipantsRecent

            subscribers = []
            offset = 0
            limit = 200
            while True:
                participants = await client(GetParticipantsRequest(
                    channel=channel.channel_id,
                    filter=ChannelParticipantsRecent(),
                    offset=offset,
                    limit=limit,
                    hash=0,
                ))
                if not participants.users:
                    break
                for user in participants.users:
                    if getattr(user, "bot", False):
                        continue
                    subscribers.append({
                        "user_id": user.id,
                        "first_name": getattr(user, "first_name", None),
                        "last_name": getattr(user, "last_name", None),
                        "username": getattr(user, "username", None),
                    })
                if len(participants.users) < limit:
                    break
                offset += limit

            return subscribers
        finally:
            db.close()

    async def import_chat_history(self, account_id: int, limit_per_dialog: int = 200) -> dict:
        """Import existing chat history from Telegram into MongoDB.

        Fetches private conversations from the connected account and stores
        messages that aren't already in MongoDB.
        """
        db = SessionLocal()
        try:
            account = db.query(TelegramAccount).filter(TelegramAccount.id == account_id).one_or_none()
            if account is None:
                raise ValueError("Account not found")

            client = await self.get_client_for_account(account)
            if client is None:
                raise ValueError("Telegram account not connected")

            imported_count = 0
            dialogs_count = 0
            chat_col = get_chat_collection()

            async for dialog in client.iter_dialogs():
                if not dialog.is_user:
                    continue
                entity = dialog.entity
                if getattr(entity, "bot", False):
                    continue

                user_id = entity.id
                display_name = " ".join(
                    part for part in [getattr(entity, "first_name", None), getattr(entity, "last_name", None)] if part
                ) or getattr(entity, "username", None)

                # Check how many messages we already have for this user
                existing_count = chat_col.count_documents(
                    {"account_id": account_id, "telegram_user_id": user_id}
                )

                # If we already have messages, skip (don't re-import)
                if existing_count > 0:
                    continue

                # Fetch messages from Telegram (oldest first)
                messages = []
                async for msg in client.iter_messages(entity, limit=limit_per_dialog):
                    if msg.text:
                        messages.append(msg)
                messages.reverse()

                if not messages:
                    continue

                dialogs_count += 1
                last_user_msg_at = None

                for msg in messages:
                    role = "assistant" if msg.out else "user"
                    store_message(account_id, user_id, role, msg.text)
                    imported_count += 1
                    if role == "user":
                        last_user_msg_at = msg.date

                # Create or update Conversation in PostgreSQL
                conversation = (
                    db.query(Conversation)
                    .filter_by(account_id=account_id, telegram_user_id=user_id)
                    .one_or_none()
                )
                if conversation is None:
                    conversation = Conversation(
                        account_id=account_id,
                        telegram_user_id=user_id,
                        display_name=display_name,
                        last_user_message_at=last_user_msg_at,
                        steps_sent=0,
                    )
                    db.add(conversation)

                # Analyze fan profile in background
                if llm_ready():
                    def _analyze(acc_id: int, u_id: int) -> None:
                        try:
                            history = get_chat_history(acc_id, u_id)
                            existing = get_fan_profile(acc_id, u_id)
                            profile = analyze_fan(history, existing)
                            if profile:
                                save_fan_profile(acc_id, u_id, profile)
                        except Exception:
                            logger.exception("Failed to analyze fan profile for user %s", u_id)

                    asyncio.get_event_loop().run_in_executor(None, _analyze, account_id, user_id)

            db.commit()
            logger.info(
                "Imported %d messages from %d dialogs for account %s",
                imported_count, dialogs_count, account_id,
            )
            return {"imported_messages": imported_count, "dialogs": dialogs_count}
        finally:
            db.close()

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
                            fan_profile = get_fan_profile(account.id, conversation.telegram_user_id)

                            # סרטונים שכבר נשלחו לפן הזה — כדי לא לחזור עליהם
                            sent_video_ids = [
                                log.video_id for log in
                                db.query(SentMessageLog)
                                .filter(
                                    SentMessageLog.conversation_id == conversation.id,
                                    SentMessageLog.video_id.isnot(None),
                                    SentMessageLog.success.is_(True),
                                ).all()
                            ]

                            result = run_follow_up_graph(
                                system_prompt=stage.system_prompt,
                                chat_history=history,
                                available_videos=video_list,
                                fan_profile=fan_profile,
                                stage_index=conversation.steps_sent,
                                personality=account.personality or "",
                                account_id=account.id,
                                telegram_user_id=conversation.telegram_user_id,
                                sent_video_ids=sent_video_ids,
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
