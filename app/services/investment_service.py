import asyncio
import logging
from datetime import datetime, timezone

from app.history import history_repository
from app.history.history_repository import HISTORY_KEYS
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
    """Atualiza dados de curvas de rendimento e salva no histórico PostgreSQL."""
    logger.info("Updating curves history...")
    try:
        await curve_service.refresh_curves()
        curves_data = curve_service.get_cache_info()
        history_repository.insert_curves(
            pre_curve=curves_data.get("pre_curve", {}),
            ipca_curve=curves_data.get("ipca_curve", {}),
            selic_rate=curves_data.get("selic_rate", 0),
            lft_vna=curves_data.get("lft_vna", 0)
        )
        logger.info("Curves history updated successfully")
        return {"status": "success", "data": "curves updated"}
    except Exception as e:
        logger.error("Failed to update curves: %s", e)
        return {"status": "error", "detail": str(e)}


async def update_inflation() -> dict:
    """Atualiza dados de IPCA/VNA e salva no histórico PostgreSQL."""
    logger.info("Updating inflation history...")
    try:
        await inflation_service.refresh_inflation()
        inflation_data = inflation_service.get_cache_info()
        history_repository.insert_inflation(
            vna=inflation_data.get("vna", 0),
            ipca_monthly=inflation_data.get("ipca_monthly", [])
        )
        logger.info("Inflation history updated successfully")
        return {"status": "success", "data": "inflation updated"}
    except Exception as e:
        logger.error("Failed to update inflation: %s", e)
        return {"status": "error", "detail": str(e)}


async def update_br_stocks() -> dict:
    """Atualiza dados de ações brasileiras e salva no histórico PostgreSQL."""
    logger.info("Updating BR stocks history...")
    tickers = get_all_tickers()
    if not tickers:
        logger.debug("No tracked BR tickers found")
        return {"status": "success", "data": {"updated": 0, "tickers": []}}

    try:
        await market_service.refresh_all_tracked_tickers()
        logger.info("BR stocks history updated for %d tickers", len(tickers))
        return {"status": "success", "data": {"updated": len(tickers), "tickers": tickers}}
    except Exception as e:
        logger.error("Failed to update BR stocks: %s", e)
        return {"status": "error", "detail": str(e)}


async def update_us_stocks() -> dict:
    """Atualiza dados de ações americanas e salva no histórico PostgreSQL."""
    logger.info("Updating US stocks history...")
    tickers = get_all_tickers_us()
    if not tickers:
        logger.debug("No tracked US tickers found")
        return {"status": "success", "data": {"updated": 0, "tickers": []}}

    try:
        for ticker in tickers:
            try:
                quote_data = await us_market_service.get_us_market_quote(ticker)
                history_repository.insert_us_stock_quote(ticker, quote_data["price"], "USD")
            except Exception as e:
                logger.warning("Failed to fetch US ticker %s: %s", ticker, e)
            await asyncio.sleep(8.0)

        logger.info("US stocks history updated for %d tickers", len(tickers))
        return {"status": "success", "data": {"updated": len(tickers), "tickers": tickers}}
    except Exception as e:
        logger.error("Failed to update US stocks: %s", e)
        return {"status": "error", "detail": str(e)}


async def update_crypto() -> dict:
    """Atualiza dados de criptomoedas e salva no histórico PostgreSQL."""
    logger.info("Updating crypto history...")
    slugs = get_all_crypto_slugs()
    if not slugs:
        logger.debug("No tracked crypto slugs found")
        return {"status": "success", "data": {"updated": 0, "slugs": []}}

    try:
        for slug in slugs:
            try:
                quote_data = await crypto_market_service.get_crypto_quote(slug)
                history_repository.insert_crypto_quote(slug.upper(), quote_data["price"], "USD")
            except Exception as e:
                logger.warning("Failed to fetch crypto %s: %s", slug, e)
            await asyncio.sleep(7.0)

        logger.info("Crypto history updated for %d slugs", len(slugs))
        return {"status": "success", "data": {"updated": len(slugs), "slugs": slugs}}
    except Exception as e:
        logger.error("Failed to update crypto: %s", e)
        return {"status": "error", "detail": str(e)}


async def update_currencies() -> dict:
    """Atualiza dados de moedas e salva no histórico PostgreSQL."""
    logger.info("Updating currencies history...")
    pairs = get_all_currency_pairs()
    if not pairs:
        logger.debug("No tracked currency pairs found")
        return {"status": "success", "data": {"updated": 0, "pairs": []}}

    updated_count = 0
    failed_pairs = []
    
    try:
        for pair in pairs:
            max_retries = 3
            retry_delay = 10  # segundos
            
            for attempt in range(max_retries):
                try:
                    base, quote = pair.split("-")
                    quote_data = await currency_service.get_currency_quote(base, quote)
                    history_repository.insert_currency_quote(pair, quote_data["price"])
                    logger.info("Currency %s updated: %s", pair, quote_data["price"])
                    updated_count += 1
                    break  # Sucesso, sai do loop de retry
                except Exception as e:
                    if attempt < max_retries - 1:
                        logger.warning("Retry %d/%d for %s: %s. Waiting %ds...", 
                            attempt + 1, max_retries, pair, e, retry_delay)
                        await asyncio.sleep(retry_delay)
                        retry_delay *= 2  # Exponential backoff
                    else:
                        logger.error("Failed to fetch currency %s after %d attempts: %s", 
                            pair, max_retries, e)
                        failed_pairs.append(pair)
            
            # Delay entre pares para evitar rate limit
            await asyncio.sleep(5.0)

        logger.info("Currencies history updated for %d/%d pairs", updated_count, len(pairs))
        if failed_pairs:
            logger.warning("Failed pairs: %s", failed_pairs)
        
        return {"status": "success" if updated_count == len(pairs) else "partial", 
                "data": {"updated": updated_count, "pairs": pairs, "failed": failed_pairs}}
    except Exception as e:
        logger.error("Failed to update currencies: %s", e)
        return {"status": "error", "detail": str(e)}


async def update_all_cache() -> dict:
    """
    Atualiza todos os dados de investimentos e salva no histórico PostgreSQL.
    Este endpoint deve ser chamado pelo cron job externo.
    """
    logger.info("Starting full history update...")
    results = {}

    results["curves"] = await update_curves()
    results["inflation"] = await update_inflation()
    results["br_stocks"] = await update_br_stocks()
    results["us_stocks"] = await update_us_stocks()
    results["crypto"] = await update_crypto()
    results["currencies"] = await update_currencies()

    cache_info = history_repository.get_updated_at()

    logger.info("Full history update completed. Updated at: %s", cache_info)

    return {
        "status": "success",
        "updated_at": cache_info,
        "results": results
    }


def get_cache_info() -> dict:
    """Retorna informações do cache persistente."""
    return history_repository.get_all()


def load_cache_to_memory() -> None:
    """Carrega o cache persistente na memória dos serviços ao iniciar a aplicação."""
    logger.info("Loading persistent cache to memory...")
    
    try:
        curves_data = history_repository.get(HISTORY_KEYS["curves"])
        if curves_data:
            curve_service._cache.pre_curve = curves_data.get("pre_curve", curve_service._cache.pre_curve)
            curve_service._cache.ipca_curve = curves_data.get("ipca_curve", curve_service._cache.ipca_curve)
            curve_service._cache.selic_rate = curves_data.get("selic_rate", curve_service._cache.selic_rate)
            curve_service._cache.lft_vna = curves_data.get("lft_vna", curve_service._cache.lft_vna)
            if curves_data.get("last_updated"):
                from datetime import datetime
                curve_service._cache.last_updated = datetime.fromisoformat(curves_data["last_updated"])
            curve_service._cache.using_fallback = curves_data.get("using_fallback", True)
            logger.info("Loaded curves cache: SELIC=%s", curve_service._cache.selic_rate)
        
        inflation_data = history_repository.get(HISTORY_KEYS["inflation"])
        if inflation_data:
            inflation_service._cache.vna = inflation_data.get("vna", inflation_service._cache.vna)
            if inflation_data.get("last_updated"):
                from datetime import datetime
                inflation_service._cache.last_updated = datetime.fromisoformat(inflation_data["last_updated"])
            inflation_service._cache.using_fallback = inflation_data.get("using_fallback", True)
            logger.info("Loaded inflation cache: VNA=%s", inflation_service._cache.vna)
        
        logger.info("Persistent cache loaded to memory successfully")
    except Exception as e:
        logger.warning("Could not load persistent cache to memory: %s", e)
        logger.info("Continuing with default in-memory cache")