import asyncio
import logging
from datetime import datetime, timezone, date as date_type, timedelta

from app.history import history_repository
from app.services import (
    curve_service, inflation_service,
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
        pre_curve, ipca_curve, selic_rate, lft_vna, _ = await curve_service.refresh_curves()
        history_repository.insert_curves(
            pre_curve=pre_curve,
            ipca_curve=ipca_curve,
            selic_rate=selic_rate,
            lft_vna=lft_vna,
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
        vna, ipca_monthly = await inflation_service.refresh_inflation()
        history_repository.insert_inflation(
            vna=vna,
            ipca_monthly=ipca_monthly,
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
                quote_data = await us_market_service.get_us_market_quote(ticker, force_refresh=True)
                history_repository.insert_us_stock_quote(ticker, quote_data["price"], "USD", recorded_at=quote_data["updated_at"])
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
                quote_data = await crypto_market_service.get_crypto_quote(slug, force_refresh=True)
                history_repository.insert_crypto_quote(slug.upper(), quote_data["price"], "USD", recorded_at=quote_data["updated_at"])
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
                    quote_data = await currency_service.get_currency_quote(base, quote, force_refresh=True)
                    history_repository.insert_currency_quote(pair, quote_data["price"], recorded_at=quote_data["updated_at"])
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


BACKFILL_START_DATE = "2026-03-01"


async def _check_has_record(table: str, asset_col: str, asset_val: str, day: date_type) -> bool:
    """Check if a record exists for the given asset on the exact date."""
    result = history_repository._execute_one(
        f"SELECT 1 FROM {table} WHERE {asset_col} = %s AND DATE(recorded_at) = %s LIMIT 1",
        (asset_val, day)
    )
    return result is not None


async def _backfill_br_stocks(start: date_type, today: date_type) -> dict:
    """Preenche lacunas no histórico de ações BR desde start até today."""
    tickers = get_all_tickers()
    filled = 0
    pending = 0
    errors: list[str] = []

    for ticker in tickers:
        current = start
        while current <= today:
            if await _check_has_record("stock_quotes_history", "ticker", ticker, current):
                current += timedelta(days=1)
                continue
            try:
                quote = await market_service.get_market_quote_by_date(ticker, current.isoformat())
                history_repository.insert_stock_quote(
                    ticker, quote["price"], "BRL",
                    recorded_at=datetime.combine(current, datetime.min.time()),
                )
                filled += 1
            except Exception as e:
                pending += 1
                logger.warning("BR stock %s on %s pending: %s", ticker, current, e)
                errors.append(f"{ticker}@{current}: {e}")

            current += timedelta(days=1)
            await asyncio.sleep(1.0)

    return {"filled": filled, "pending": pending, "tickers": len(tickers), "errors": errors[:10]}


async def _backfill_us_stocks(start: date_type, today: date_type) -> dict:
    """Preenche lacunas no histórico de ações US desde start até today."""
    tickers = get_all_tickers_us()
    filled = 0
    pending = 0
    errors: list[str] = []

    for ticker in tickers:
        current = start
        while current <= today:
            if await _check_has_record("stock_quotes_us_history", "ticker", ticker, current):
                current += timedelta(days=1)
                continue
            try:
                quote = await us_market_service.get_us_market_quote_by_date(ticker, current.isoformat())
                history_repository.insert_us_stock_quote(
                    ticker, quote["price"], "USD",
                    recorded_at=datetime.combine(current, datetime.min.time()),
                )
                filled += 1
                current += timedelta(days=1)
                await asyncio.sleep(8.0)
            except Exception as e:
                error_msg = str(e)
                if "Rate limit" in error_msg or "429" in error_msg:
                    wait = 61 - datetime.now(timezone.utc).second
                    logger.warning("US stock %s on %s rate limited. Waiting %ds until next minute...", ticker, current, wait)
                    await asyncio.sleep(wait)
                elif "No data is available" in error_msg:
                    previous = history_repository.get_us_stock_quote_by_date(
                        ticker, (current - timedelta(days=1)).isoformat()
                    )
                    if previous is not None:
                        history_repository.insert_us_stock_quote(
                            ticker, float(previous["unit_price"]), "USD",
                            recorded_at=datetime.combine(current, datetime.min.time()),
                        )
                        filled += 1
                        logger.info("US stock %s on %s reused price %.2f from previous day (no API data)",
                                    ticker, current, float(previous["unit_price"]))
                    else:
                        pending += 1
                        logger.warning("US stock %s on %s no API data and no previous price available", ticker, current)
                        errors.append(f"{ticker}@{current}: {e}")
                    current += timedelta(days=1)
                    await asyncio.sleep(8.0)
                else:
                    pending += 1
                    logger.warning("US stock %s on %s pending: %s", ticker, current, e)
                    errors.append(f"{ticker}@{current}: {e}")
                    current += timedelta(days=1)
                    await asyncio.sleep(8.0)

    return {"filled": filled, "pending": pending, "tickers": len(tickers), "errors": errors[:10]}


async def _backfill_currencies(start: date_type, today: date_type) -> dict:
    """Preenche lacunas no histórico de moedas desde start até today."""
    pairs = get_all_currency_pairs()
    filled = 0
    pending = 0
    errors: list[str] = []

    for pair in pairs:
        parts = pair.split("-")
        if len(parts) != 2:
            logger.warning("Invalid currency pair: %s", pair)
            continue

        from_cur, to_cur = parts[0], parts[1]
        current = start
        while current <= today:
            if await _check_has_record("currency_quotes_history", "currency_pair", pair, current):
                current += timedelta(days=1)
                continue
            try:
                await currency_service.get_currency_quote_by_date(from_cur, to_cur, current.isoformat())
                filled += 1
            except Exception as e:
                pending += 1
                logger.warning("Currency %s on %s pending: %s", pair, current, e)
                errors.append(f"{pair}@{current}: {e}")

            current += timedelta(days=1)
            await asyncio.sleep(1.0)

    return {"filled": filled, "pending": pending, "pairs": len(pairs), "errors": errors[:10]}


async def verify_and_backfill(start_date: str = BACKFILL_START_DATE) -> dict:
    """
    Verifica se há registros de cotação para todos os ativos desde start_date
    e preenche lacunas chamando as APIs externas.

    Roda a cada execução do cron: na primeira vez após o cleanup, preenche todo
    o histórico; nas execuções seguintes, só complementa os dias faltantes.
    """
    start = datetime.strptime(start_date, "%Y-%m-%d").date()
    today = datetime.now(timezone.utc).date()

    logger.info("Starting backfill verification from %s to %s", start, today)

    results = {
        "period": {"from": start_date, "to": today.isoformat()},
        "br_stocks": await _backfill_br_stocks(start, today),
        "us_stocks": await _backfill_us_stocks(start, today),
        "currencies": await _backfill_currencies(start, today),
    }

    total_filled = (
        results["br_stocks"]["filled"]
        + results["us_stocks"]["filled"]
        + results["currencies"]["filled"]
    )
    total_pending = (
        results["br_stocks"]["pending"]
        + results["us_stocks"]["pending"]
        + results["currencies"]["pending"]
    )
    logger.info("Backfill complete: %d filled, %d pending", total_filled, total_pending)

    return results


def deduplicate_all_history() -> dict:
    """
    Remove registros duplicados de todas as tabelas de histórico.
    Mantém apenas o registro mais recente de cada dia (por ativo, quando aplicável).
    """
    logger.info("Starting history deduplication...")
    result = history_repository.deduplicate_all_tables()
    logger.info("History deduplication complete: %s", result)
    return result


async def update_all_cache() -> dict:
    """
    Atualiza todos os dados de investimentos e salva no histórico PostgreSQL.
    Este endpoint deve ser chamado pelo cron job externo.

    0. Remove registros duplicados de todas as tabelas de histórico
    1. Verifica lacunas nas 3 tabelas de cotação (backfill desde 01/03/2026)
    2. Salva os dados mais recentes de todas as categorias
    """
    logger.info("Starting full history update...")
    results = {}

    results["dedup"] = deduplicate_all_history()
    results["backfill"] = await verify_and_backfill()

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


