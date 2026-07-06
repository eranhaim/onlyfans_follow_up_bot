import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import settings
from app.telegram_service import telegram_service

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()


async def follow_up_job() -> None:
    try:
        sent = await telegram_service.run_follow_ups()
        if sent:
            logger.info("Sent %s follow-up message(s)", sent)
    except Exception:
        logger.exception("Follow-up job failed")


def start_scheduler() -> None:
    scheduler.add_job(
        follow_up_job,
        "interval",
        seconds=settings.scheduler_interval_seconds,
        id="follow_up_job",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Scheduler started (every %ss)", settings.scheduler_interval_seconds)


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
