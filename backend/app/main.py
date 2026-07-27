import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import SessionLocal, TelegramAccount, init_db
from app.mongo import init_mongo
from app.routes import router
from app.scheduler import start_scheduler, stop_scheduler
from app.simulator_routes import router as simulator_router
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
    finally:
        db.close()


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    init_mongo()
    seed_defaults()
    start_scheduler()
    await telegram_service.connect_all()
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
app.include_router(simulator_router)
