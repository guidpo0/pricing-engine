"""
APScheduler background jobs for refreshing market data.

Jobs run as coroutines scheduled via AsyncIOScheduler so they
integrate seamlessly with FastAPI's async event loop.
"""
from __future__ import annotations

import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import settings
from app.services import curve_service, inflation_service

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


async def _update_curves_job() -> None:
    logger.info("[job] Updating yield curves...")
    await curve_service.refresh_curves()


async def _update_inflation_job() -> None:
    logger.info("[job] Updating IPCA / VNA...")
    await inflation_service.refresh_inflation()


async def run_initial_data_load() -> None:
    """Fetch market data immediately at startup (before the scheduler fires)."""
    logger.info("Running initial market data load...")
    results = await asyncio.gather(
        curve_service.refresh_curves(),
        inflation_service.refresh_inflation(),
        return_exceptions=True,
    )
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.warning("Initial data load task %d failed: %s", i, result)
    logger.info("Initial market data load complete.")


def start_scheduler() -> AsyncIOScheduler:
    """Create, configure and start the background scheduler."""
    global _scheduler  # noqa: PLW0603
    _scheduler = AsyncIOScheduler()

    _scheduler.add_job(
        _update_curves_job,
        trigger=CronTrigger(hour=settings.curve_update_hour, minute=0, timezone="UTC"),
        id="update_curves",
        name="Update ANBIMA yield curves",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    _scheduler.add_job(
        _update_inflation_job,
        trigger=CronTrigger(hour=settings.ipca_update_hour, minute=0, timezone="UTC"),
        id="update_inflation",
        name="Update BCB IPCA / VNA",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    _scheduler.start()
    logger.info(
        "Scheduler started. Curves at %sh UTC, IPCA at %sh UTC.",
        settings.curve_update_hour,
        settings.ipca_update_hour,
    )
    return _scheduler


def stop_scheduler() -> None:
    """Gracefully shut down the scheduler."""
    global _scheduler  # noqa: PLW0603
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped.")
