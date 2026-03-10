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
from app.services import (
    curve_service, inflation_service, cdb_service, market_service,
    us_market_service, crypto_market_service, currency_service
)

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


async def _update_curves_job() -> None:
    logger.info("[job] Updating yield curves...")
    await curve_service.refresh_curves()


async def _update_inflation_job() -> None:
    logger.info("[job] Updating IPCA / VNA...")
    await inflation_service.refresh_inflation()


async def _update_cdb_rates_job() -> None:
    logger.info("[job] Updating CDI daily factors...")
    await cdb_service.refresh_cdb_rates()


async def _refresh_tickers_job() -> None:
    logger.info("[job] Refreshing background tracked tickers...")
    await market_service.refresh_all_tracked_tickers()

async def _refresh_us_tickers_job() -> None:
    from app.utils.database import get_all_tickers_us
    tickers = get_all_tickers_us()
    if not tickers:
        return
    logger.info("[job] Refreshing %d US background tracked tickers...", len(tickers))
    for ticker in tickers:
        try:
            await us_market_service.get_us_market_quote(ticker)
        except Exception as e:
            logger.error("Failed to refresh US ticker %s: %s", ticker, e)
        # Delay to respect TwelveData rate limit (~8 requests/min)
        await asyncio.sleep(8.0)

async def _refresh_crypto_job() -> None:
    from app.utils.database import get_all_crypto_slugs
    slugs = get_all_crypto_slugs()
    if not slugs:
        return
    logger.info("[job] Refreshing %d crypto background tracked slugs...", len(slugs))
    for slug in slugs:
        try:
            await crypto_market_service.get_crypto_quote(slug)
        except Exception as e:
            logger.error("Failed to refresh Crypto slug %s: %s", slug, e)
        # Delay to respect CoinMarketCap rate limit
        await asyncio.sleep(7.0)

async def _refresh_currency_job() -> None:
    from app.utils.database import get_all_currency_pairs
    pairs = get_all_currency_pairs()
    if not pairs:
        return
    logger.info("[job] Refreshing %d currency background tracked pairs...", len(pairs))
    for pair in pairs:
        try:
            base, quote = pair.split("-")
            await currency_service.get_currency_quote(base, quote)
        except Exception as e:
            logger.error("Failed to refresh Currency pair %s: %s", pair, e)
        # Small delay for safety
        await asyncio.sleep(2.0)

async def run_initial_data_load() -> None:
    """Fetch market data immediately at startup (before the scheduler fires)."""
    logger.info("Running initial market data load...")
    # Execute fast / parallel updates
    results = await asyncio.gather(
        curve_service.refresh_curves(),
        inflation_service.refresh_inflation(),
        cdb_service.refresh_cdb_rates(),
        market_service.refresh_all_tracked_tickers(),
        return_exceptions=True,
    )
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.warning("Initial data load task %d failed: %s", i, result)
    
    # Execute rate-limited background tasks without gathering to not block API startup indefinitely
    # Create background tasks for these instead of waiting.
    asyncio.create_task(_refresh_us_tickers_job())
    asyncio.create_task(_refresh_crypto_job())
    asyncio.create_task(_refresh_currency_job())

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

    _scheduler.add_job(
        _update_cdb_rates_job,
        trigger=CronTrigger(hour=settings.curve_update_hour, minute=30, timezone="UTC"),
        id="update_cdb_rates",
        name="Update CDI daily factors",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    _scheduler.add_job(
        _refresh_tickers_job,
        trigger="interval",
        minutes=15,
        id="refresh_tickers",
        name="Refresh tracked tickers",
        replace_existing=True,
    )
    
    _scheduler.add_job(
        _refresh_us_tickers_job,
        trigger="interval",
        minutes=20,
        id="refresh_us_tickers",
        name="Refresh tracked US tickers",
        replace_existing=True,
    )

    _scheduler.add_job(
        _refresh_crypto_job,
        trigger="interval",
        minutes=20,
        id="refresh_crypto",
        name="Refresh tracked Crypto slugs",
        replace_existing=True,
    )

    _scheduler.add_job(
        _refresh_currency_job,
        trigger="interval",
        minutes=15,
        id="refresh_currency",
        name="Refresh tracked Currency pairs",
        replace_existing=True,
    )

    _scheduler.start()
    logger.info(
        "Scheduler started. Curves at %sh UTC, IPCA at %sh UTC, Tickers every 15min.",
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
