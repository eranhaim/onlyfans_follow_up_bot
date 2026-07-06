import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import FollowUpStep, SessionLocal, TelegramAccount, init_db
from app.routes import router
from app.scheduler import start_scheduler, stop_scheduler
from app.telegram_service import telegram_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def seed_defaults() -> None:
    db = SessionLocal()
    try:
        if db.query(TelegramAccount).count() == 0 and settings.telegram_session_string:
            db.add(
                TelegramAccount(
                    name="Model",
                    session_string=settings.telegram_session_string,
                    is_connected=True,
                )
            )
            db.commit()

        if db.query(FollowUpStep).count() == 0:
            db.add_all(
                [
                    FollowUpStep(
                        position=0,
                        delay_hours=24,
                        message_text="Hey! I noticed you stopped by — anything I can help you with? 😊",
                        is_active=True,
                    ),
                    FollowUpStep(
                        position=1,
                        delay_hours=48,
                        message_text="Still thinking about it? I have something special waiting for you 💕",
                        is_active=True,
                    ),
                ]
            )
            db.commit()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    seed_defaults()
    start_scheduler()
    await telegram_service.get_client()
    logger.info("Follow-up bot started")
    yield
    stop_scheduler()
    await telegram_service.disconnect()


app = FastAPI(title="Follow-Up Bot", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin, "http://localhost:5173", "http://localhost:8087"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
