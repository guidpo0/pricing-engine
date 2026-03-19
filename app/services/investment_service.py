import asyncio
import logging
from datetime import datetime, timezone

from app.cache import cache_repository
from app.cache.cache_repository import CACHE_KEYS
from app.config import settings
from app.services import (
    curve_service, inflation_service, cdb_service,
    market_service, us_market_service, crypto_market_service,
    currency_service
)
from app.utils.database import (
    get_all_tickers, get_all_tickers_us,
    get_all_crypto_slugs, get_all_currency_pairs
)

logger = logging.getLogger(__name__)


async def update_curves() -> dict:
    """Atualiza dados de curvas de rendimento e salva no cache persistente."""
    logger.info("Updating curves cache...")
    try:
        await curve_service.refresh_curves()
        curves_data = curve_service.get_cache_info()
        cache_repository.set(CACHE_KEYS["curves"], curves_data)
        logger.info("Curves cache updated successfully")
        return {"status": "success", "data": "curves updated"}
    except Exception as e:
        logger.error("Failed to update curves: %s", e)
        return {"status": "error", "detail": str(e)}


async def update_inflation() -> dict:
    """Atualiza dados de IPCA/VNA e salva no cache persistente."""
    logger.info("Updating inflation cache...")
    try:
        await inflation_service.refresh_inflation()
        inflation_data = inflation_service.get_cache_info()
        cache_repository.set(CACHE_KEYS["inflation"], inflation_data)
        logger.info("Inflation cache updated successfully")
        return {"status": "success", "data": "inflation updated"}
    except Exception as e:
        logger.error("Failed to update inflation: %s", e)
        return {"status": "error", "detail": str(e)}


async def update_br_stocks() -> dict:
    """Atualiza dados de ações brasileiras e salva no cache persistente."""
    logger.info("Updating BR stocks cache...")
    tickers = get_all_tickers()
    if not tickers:
        logger.debug("No tracked BR tickers found")
        return {"status": "success", "data": {"updated": 0, "tickers": []}}

    try:
        await market_service.refresh_all_tracked_tickers()
        br_stocks_data = {
            "tickers": tickers,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        cache_repository.set(CACHE_KEYS["br_stocks"], br_stocks_data)
        logger.info("BR stocks cache updated for %d tickers", len(tickers))
        return {"status": "success", "data": {"updated": len(tickers), "tickers": tickers}}
    except Exception as e:
        logger.error("Failed to update BR stocks: %s", e)
        return {"status": "error", "detail": str(e)}


async def update_us_stocks() -> dict:
    """Atualiza dados de ações americanas e salva no cache persistente."""
    logger.info("Updating US stocks cache...")
    tickers = get_all_tickers_us()
    if not tickers:
        logger.debug("No tracked US tickers found")
        return {"status": "success", "data": {"updated": 0, "tickers": []}}

    try:
        for ticker in tickers:
            try:
                await us_market_service.get_us_market_quote(ticker)
            except Exception as e:
                logger.warning("Failed to fetch US ticker %s: %s", ticker, e)
            await asyncio.sleep(8.0)

        us_stocks_data = {
            "tickers": tickers,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        cache_repository.set(CACHE_KEYS["us_stocks"], us_stocks_data)
        logger.info("US stocks cache updated for %d tickers", len(tickers))
        return {"status": "success", "data": {"updated": len(tickers), "tickers": tickers}}
    except Exception as e:
        logger.error("Failed to update US stocks: %s", e)
        return {"status": "error", "detail": str(e)}


async def update_crypto() -> dict:
    """Atualiza dados de criptomoedas e salva no cache persistente."""
    logger.info("Updating crypto cache...")
    slugs = get_all_crypto_slugs()
    if not slugs:
        logger.debug("No tracked crypto slugs found")
        return {"status": "success", "data": {"updated": 0, "slugs": []}}

    try:
        for slug in slugs:
            try:
                await crypto_market_service.get_crypto_quote(slug)
            except Exception as e:
                logger.warning("Failed to fetch crypto %s: %s", slug, e)
            await asyncio.sleep(7.0)

        crypto_data = {
            "slugs": slugs,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        cache_repository.set(CACHE_KEYS["crypto"], crypto_data)
        logger.info("Crypto cache updated for %d slugs", len(slugs))
        return {"status": "success", "data": {"updated": len(slugs), "slugs": slugs}}
    except Exception as e:
        logger.error("Failed to update crypto: %s", e)
        return {"status": "error", "detail": str(e)}


async def update_currencies() -> dict:
    """Atualiza dados de moedas e salva no cache persistente."""
    logger.info("Updating currencies cache...")
    pairs = get_all_currency_pairs()
    if not pairs:
        logger.debug("No tracked currency pairs found")
        return {"status": "success", "data": {"updated": 0, "pairs": []}}

    try:
        for pair in pairs:
            try:
                base, quote = pair.split("-")
                await currency_service.get_currency_quote(base, quote)
            except Exception as e:
                logger.warning("Failed to fetch currency %s: %s", pair, e)
            await asyncio.sleep(2.0)

        currencies_data = {
            "pairs": pairs,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        cache_repository.set(CACHE_KEYS["currencies"], currencies_data)
        logger.info("Currencies cache updated for %d pairs", len(pairs))
        return {"status": "success", "data": {"updated": len(pairs), "pairs": pairs}}
    except Exception as e:
        logger.error("Failed to update currencies: %s", e)
        return {"status": "error", "detail": str(e)}


async def update_all_cache() -> dict:
    """
    Atualiza todos os dados de investimentos e salva no cache persistente.
    Este endpoint deve ser chamado pelo cron job externo.
    """
    logger.info("Starting full cache update...")
    results = {}

    results["curves"] = await update_curves()
    results["inflation"] = await update_inflation()
    results["br_stocks"] = await update_br_stocks()
    results["us_stocks"] = await update_us_stocks()
    results["crypto"] = await update_crypto()
    results["currencies"] = await update_currencies()

    cache_info = cache_repository.get_all()

    logger.info("Full cache update completed. Updated at: %s", cache_info.get("updated_at"))

    return {
        "status": "success",
        "updated_at": cache_info.get("updated_at"),
        "results": results
    }


def get_cache_info() -> dict:
    """Retorna informações do cache persistente."""
    return cache_repository.get_all()