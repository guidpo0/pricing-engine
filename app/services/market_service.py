import logging
from datetime import datetime, timedelta, timezone
import httpx
import asyncio
from typing import Dict, Any, Optional

from app.config import settings
from app.utils.database import add_ticker, get_all_tickers
from app.history.history_repository import history_repository

logger = logging.getLogger(__name__)

# Simple thread-safe in-memory cache
_quote_cache: Dict[str, Any] = {}
CACHE_TTL_SECONDS = 30 * 60  # 30 minutes
MAX_RETRIES = 3

# Rate limiting mechanism for BRAPI
# Brapi Free tier allows limited requests per second
_brapi_lock = asyncio.Lock()
_last_request_time: float = 0.0
MIN_REQUEST_INTERVAL_SECONDS = 1.0  # Wait at least 1s between requests

def _get_from_cache(ticker: str) -> Optional[float]:
    """Retrieve quote from cache if available and not expired."""
    now = datetime.now(timezone.utc).timestamp()
    if ticker in _quote_cache:
        entry = _quote_cache[ticker]
        if now < entry["expires_at"]:
            return entry["price"]
        else:
            del _quote_cache[ticker]
    return None

def _set_in_cache(ticker: str, price: float) -> None:
    """Store quote in cache."""
    now = datetime.now(timezone.utc)
    _quote_cache[ticker] = {
        "price": price,
        "updated_at": now,
        "expires_at": now.timestamp() + CACHE_TTL_SECONDS
    }

async def get_market_quote(ticker: str, force_refresh: bool = False) -> dict:
    """
    Fetch market quote for a given ticker from BRAPI or cache/database.
    Retries up to 3 times on 429 or 5xx errors with exponential backoff.
    Saves all quotes to PostgreSQL history.
    """
    ticker = ticker.upper()
    
    # Store ticker in the background DB for future automatic refreshes
    add_ticker(ticker)
    
    db_quote = None
    
    if not force_refresh:
        # Try to get from in-memory cache first
        cached_price = _get_from_cache(ticker)
        
        if cached_price is not None:
            logger.debug("Quote for %s found in memory cache", ticker)
            return {
                "price": cached_price,
                "updated_at": _quote_cache[ticker]["updated_at"]
            }

        # Try to get from database (latest historical record)
        db_quote = history_repository.get_latest_stock_quote(ticker)
        if db_quote:
            logger.debug("Quote for %s found in database", ticker)
            _set_in_cache(ticker, float(db_quote["unit_price"]))
            return {
                "price": float(db_quote["unit_price"]),
                "updated_at": db_quote["recorded_at"]
            }

    url = f"{settings.brapi_base_url}/quote/{ticker}"
    params = {}
    if settings.brapi_token:
        params["token"] = settings.brapi_token

    async with httpx.AsyncClient(timeout=settings.http_timeout) as client:
        for attempt in range(MAX_RETRIES):
            try:
                # Apply rate limiting
                global _last_request_time
                async with _brapi_lock:
                    now = asyncio.get_event_loop().time()
                    time_since_last = now - _last_request_time
                    if time_since_last < MIN_REQUEST_INTERVAL_SECONDS:
                        await asyncio.sleep(MIN_REQUEST_INTERVAL_SECONDS - time_since_last)
                    
                    _last_request_time = asyncio.get_event_loop().time()
                    response = await client.get(url, params=params)
                
                if response.status_code == 200:
                    data = response.json()
                    
                    if "results" not in data or not data["results"]:
                        raise ValueError(f"No results found for ticker {ticker}")
                    
                    result = data["results"][0]
                    if "regularMarketPrice" not in result:
                        raise ValueError(f"Price data missing for ticker {ticker}")
                        
                    price = float(result["regularMarketPrice"])
                    
                    _set_in_cache(ticker, price)
                    
                    return {
                        "price": price,
                        "updated_at": _quote_cache[ticker]["updated_at"]
                    }
                
                elif response.status_code == 429 or response.status_code >= 500:
                    # Retry logic for Rate Limit or Server Errors
                    logger.warning(
                        "Attempt %d/%d failed for %s. Status %d. Retrying...", 
                        attempt + 1, MAX_RETRIES, ticker, response.status_code
                    )
                    if attempt < MAX_RETRIES - 1:
                        await asyncio.sleep(2 ** attempt)  # Exponential backoff: 1, 2...
                    else:
                        raise ValueError(f"Failed to fetch quote for {ticker} after {MAX_RETRIES} attempts. Status: {response.status_code}")
                elif response.status_code == 404:
                    raise ValueError(f"Ticker {ticker} not found")
                else:
                    response.raise_for_status()
                    
            except httpx.RequestError as e:
                logger.error("Request error for %s on attempt %d: %s", ticker, attempt + 1, e)
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(2 ** attempt)
                else:
                    raise ValueError(f"Network error fetching quote for {ticker}: {str(e)}") from e


    raise ValueError(f"Unexpected error fetching quote for {ticker}")

async def refresh_all_tracked_tickers() -> None:
    """
    Background worker function to iterate through all tracked tickers,
    fetch from BRAPI, and populate the in-memory cache proactively.
    """
    tickers = get_all_tickers()
    if not tickers:
        logger.debug("No tracked tickers found for background update.")
        return
        
    logger.info("[market_service] Automatically refreshing %d tracked tickers...", len(tickers))
    
    # We MUST reuse httpx AsyncClient to iterate cleanly and efficiently
    url_base = f"{settings.brapi_base_url}/quote/"
    params = {}
    if settings.brapi_token:
        params["token"] = settings.brapi_token
        
    async with httpx.AsyncClient(timeout=settings.http_timeout) as client:
        for ticker in tickers:
            url = f"{url_base}{ticker}"
            for attempt in range(MAX_RETRIES):
                try:
                    global _last_request_time
                    async with _brapi_lock:
                        now = asyncio.get_event_loop().time()
                        time_since_last = now - _last_request_time
                        if time_since_last < MIN_REQUEST_INTERVAL_SECONDS:
                            await asyncio.sleep(MIN_REQUEST_INTERVAL_SECONDS - time_since_last)
                        
                        _last_request_time = asyncio.get_event_loop().time()
                        response = await client.get(url, params=params)
                        
                    if response.status_code == 200:
                        data = response.json()
                        if "results" in data and data["results"]:
                            result = data["results"][0]
                            if "regularMarketPrice" in result:
                                price = float(result["regularMarketPrice"])
                                _set_in_cache(ticker, price)
                                history_repository.insert_stock_quote(ticker, price)
                                logger.debug("Refreshed %s successfully.", ticker)
                        break  # Break retry loop on success
                        
                    elif response.status_code == 429 or response.status_code >= 500:
                        if attempt < MAX_RETRIES - 1:
                            await asyncio.sleep(2 ** attempt)
                        else:
                            logger.error("Failed to refresh %s in background (Status %d)", ticker, response.status_code)
                    
                    elif response.status_code == 404:
                        logger.warning("Ticker %s not found on BRAPI during background refresh", ticker)
                        break # Break retry loop, ticker is invalid
                        
                except httpx.RequestError as e:
                    if attempt < MAX_RETRIES - 1:
                        await asyncio.sleep(2 ** attempt)
                    else:
                        logger.error("Network error refreshing %s in background: %s", ticker, e)
                        
    logger.info("[market_service] Completed background refresh of tickers.")


async def get_market_quote_by_date(ticker: str, date: str) -> dict:
    """
    Fetch historical market quote for a given ticker from BRAPI for a specific date.
    Uses the range/interval parameters to get historical OHLCV data.
    """
    ticker = ticker.upper()
    add_ticker(ticker)

    url = f"{settings.brapi_base_url}/quote/{ticker}"
    params: dict[str, Any] = {"range": "3mo", "interval": "1d", "fundamental": "false"}
    if settings.brapi_token:
        params["token"] = settings.brapi_token

    date_target = datetime.strptime(date, "%Y-%m-%d").date()
    start_date = (date_target - timedelta(days=60)).strftime("%Y-%m-%d")
    end_date = date

    params["startDate"] = start_date
    params["endDate"] = end_date
    params.pop("range", None)
    logger.info("Fetching quote for %s with window %s to %s", ticker, start_date, end_date)

    async with httpx.AsyncClient(timeout=settings.http_timeout) as client:
        for attempt in range(MAX_RETRIES):
            try:
                async with _brapi_lock:
                    global _last_request_time
                    now = asyncio.get_event_loop().time()
                    time_since_last = now - _last_request_time
                    if time_since_last < MIN_REQUEST_INTERVAL_SECONDS:
                        await asyncio.sleep(MIN_REQUEST_INTERVAL_SECONDS - time_since_last)
                    _last_request_time = asyncio.get_event_loop().time()
                    response = await client.get(url, params=params)

                if response.status_code == 200:
                    data = response.json()
                    results = data.get("results", [])
                    if not results:
                        raise ValueError(f"No results found for ticker {ticker}")

                    hist_data = results[0].get("historicalDataPrice", [])
                    if not hist_data:
                        raise ValueError(f"No historical data found for ticker {ticker}")

                    best: dict[str, Any] | None = None
                    for item in hist_data:
                        item_date = datetime.fromtimestamp(item["date"]).date()
                        if item_date <= date_target:
                            if best is None or item_date > best["date"]:
                                best = {"date": item_date, "close": float(item["close"])}

                    if best is None:
                        raise ValueError(f"No quote found for {ticker} on or before {date}")

                    logger.info("Historical quote for %s on %s: %.2f", ticker, best["date"], best["close"])
                    return {
                        "price": best["close"],
                        "updated_at": best["date"].isoformat()
                    }

                elif response.status_code == 429 or response.status_code >= 500:
                    logger.warning(
                        "Attempt %d/%d failed for %s (historical). Status %d. Retrying...",
                        attempt + 1, MAX_RETRIES, ticker, response.status_code
                    )
                    if attempt < MAX_RETRIES - 1:
                        await asyncio.sleep(2 ** attempt)
                    else:
                        raise ValueError(f"Failed to fetch historical quote for {ticker} after {MAX_RETRIES} attempts. Status: {response.status_code}")
                elif response.status_code == 404:
                    raise ValueError(f"Ticker {ticker} not found")
                else:
                    response.raise_for_status()

            except httpx.RequestError as e:
                logger.error("Request error for %s (historical) on attempt %d: %s", ticker, attempt + 1, e)
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(2 ** attempt)
                else:
                    raise ValueError(f"Network error fetching historical quote for {ticker}: {str(e)}") from e

    raise ValueError(f"No quote found for {ticker} on or before {date}")


async def get_batch_market_quotes(tickers: list[dict]) -> list[dict]:
    """
    Fetch quotes for multiple tickers in a single batch call.
    Groups by market and uses efficient external API calls.
    """
    results: list[dict] = []

    br_items = [t for t in tickers if t.get("market", "br") == "br"]
    us_items = [t for t in tickers if t.get("market") == "us"]
    crypto_items = [t for t in tickers if t.get("market") == "crypto"]

    if br_items:
        br_results = await _get_batch_br_quotes(br_items)
        results.extend(br_results)

    for item in us_items:
        ticker = item["ticker"].upper()
        try:
            cached = _get_from_cache(ticker)
            if cached is not None:
                results.append({"ticker": ticker, "unit_price": cached, "market": "us", "updated_at": _quote_cache[ticker]["updated_at"], "error": None})
                continue

            db_quote = history_repository.get_latest_us_stock_quote(ticker)
            if db_quote:
                _set_in_cache(ticker, float(db_quote["unit_price"]))
                results.append({"ticker": ticker, "unit_price": float(db_quote["unit_price"]), "market": "us", "updated_at": db_quote["recorded_at"], "error": None})
                continue

            quote = await get_us_market_quote(ticker)
            results.append({"ticker": ticker, "unit_price": quote["price"], "market": "us", "updated_at": quote["updated_at"], "error": None})
        except Exception as e:
            results.append({"ticker": ticker, "unit_price": None, "market": "us", "updated_at": None, "error": str(e)})

    if crypto_items:
        crypto_results = await _get_batch_crypto_quotes(crypto_items)
        results.extend(crypto_results)

    return results


async def _get_batch_br_quotes(items: list[dict]) -> list[dict]:
    """Fetch multiple BR tickers from cache/db/BRAPI in a single call."""
    results: list[dict] = []
    missing: list[str] = []

    for item in items:
        ticker = item["ticker"].upper()
        cached = _get_from_cache(ticker)
        if cached is not None:
            results.append({"ticker": ticker, "unit_price": cached, "market": "br", "updated_at": _quote_cache[ticker]["updated_at"], "error": None})
            continue

        db_quote = history_repository.get_latest_stock_quote(ticker)
        if db_quote:
            _set_in_cache(ticker, float(db_quote["unit_price"]))
            results.append({"ticker": ticker, "unit_price": float(db_quote["unit_price"]), "market": "br", "updated_at": db_quote["recorded_at"], "error": None})
            continue

        missing.append(ticker)

    if not missing:
        return results

    for ticker in missing:
        add_ticker(ticker)

    tickers_str = ",".join(missing)
    url = f"{settings.brapi_base_url}/quote/{tickers_str}"
    params = {}
    if settings.brapi_token:
        params["token"] = settings.brapi_token

    async with httpx.AsyncClient(timeout=settings.http_timeout) as client:
        for attempt in range(MAX_RETRIES):
            try:
                global _last_request_time
                async with _brapi_lock:
                    now = asyncio.get_event_loop().time()
                    time_since_last = now - _last_request_time
                    if time_since_last < MIN_REQUEST_INTERVAL_SECONDS:
                        await asyncio.sleep(MIN_REQUEST_INTERVAL_SECONDS - time_since_last)
                    _last_request_time = asyncio.get_event_loop().time()
                    response = await client.get(url, params=params)

                if response.status_code == 200:
                    data = response.json()
                    fetched = {r["symbol"]: r.get("regularMarketPrice") for r in data.get("results", []) if r.get("symbol")}
                    for ticker in missing:
                        price = fetched.get(ticker)
                        if price is not None:
                            _set_in_cache(ticker, float(price))
                            results.append({"ticker": ticker, "unit_price": float(price), "market": "br", "updated_at": _quote_cache[ticker]["updated_at"], "error": None})
                        else:
                            results.append({"ticker": ticker, "unit_price": None, "market": "br", "updated_at": None, "error": f"Price not found for {ticker}"})
                    return results

                elif response.status_code == 429 or response.status_code >= 500:
                    logger.warning("Batch BRAPI attempt %d/%d failed. Status %d. Retrying...", attempt + 1, MAX_RETRIES, response.status_code)
                    if attempt < MAX_RETRIES - 1:
                        await asyncio.sleep(2 ** attempt)
                    else:
                        for ticker in missing:
                            results.append({"ticker": ticker, "unit_price": None, "market": "br", "updated_at": None, "error": f"Rate limited after {MAX_RETRIES} attempts"})
                    continue
                else:
                    response.raise_for_status()

            except httpx.RequestError as e:
                logger.error("Request error in batch BRAPI on attempt %d: %s", attempt + 1, e)
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(2 ** attempt)
                else:
                    for ticker in missing:
                        results.append({"ticker": ticker, "unit_price": None, "market": "br", "updated_at": None, "error": str(e)})

    return results


async def _get_batch_crypto_quotes(items: list[dict]) -> list[dict]:
    """Fetch multiple crypto quotes from cache/db/CoinMarketCap."""
    from app.services.crypto_market_service import _get_from_cache as _crypto_get_cache, _set_in_cache as _crypto_set_cache

    results: list[dict] = []
    missing: list[str] = []

    for item in items:
        slug = item["ticker"].lower()
        cached = _crypto_get_cache(slug)
        if cached is not None:
            results.append({"ticker": slug, "unit_price": cached, "market": "crypto", "updated_at": None, "error": None})
            continue

        db_quote = history_repository.get_latest_crypto_quote(slug)
        if db_quote:
            _crypto_set_cache(slug, float(db_quote["unit_price"]))
            results.append({"ticker": slug, "unit_price": float(db_quote["unit_price"]), "market": "crypto", "updated_at": db_quote["recorded_at"], "error": None})
            continue

        missing.append(slug)

    if not missing:
        return results

    for slug in missing:
        from app.utils.database import add_crypto_slug
        add_crypto_slug(slug)

    slugs_str = ",".join(missing)
    url = f"{settings.coin_market_base_url}/v2/cryptocurrency/quotes/latest"
    params = {"slug": slugs_str}
    headers = {"X-CMC_PRO_API_KEY": settings.coin_market_api_token}

    async with httpx.AsyncClient(timeout=settings.http_timeout) as client:
        for attempt in range(MAX_RETRIES):
            try:
                response = await client.get(url, params=params, headers=headers)

                if response.status_code == 200:
                    data = response.json()
                    if "data" in data and data["data"]:
                        for coin in data["data"].values():
                            slug = coin.get("slug", "").lower()
                            if "quote" in coin and "USD" in coin["quote"]:
                                price = float(coin["quote"]["USD"]["price"])
                                _crypto_set_cache(slug, price)
                                for r in results:
                                    if r["ticker"] == slug:
                                        r["unit_price"] = price
                                        break
                                else:
                                    results.append({"ticker": slug, "unit_price": price, "market": "crypto", "updated_at": None, "error": None})
                                if slug in missing:
                                    missing.remove(slug)
                    for slug in missing:
                        results.append({"ticker": slug, "unit_price": None, "market": "crypto", "updated_at": None, "error": "Price not found"})
                    return results

                elif response.status_code == 429:
                    logger.warning("CMC rate limit on batch crypto request")
                    for slug in missing:
                        results.append({"ticker": slug, "unit_price": None, "market": "crypto", "updated_at": None, "error": "Rate limited"})
                    return results

                elif response.status_code >= 500:
                    logger.warning("CMC attempt %d/%d failed. Status %d", attempt + 1, MAX_RETRIES, response.status_code)
                    if attempt < MAX_RETRIES - 1:
                        await asyncio.sleep(2 ** attempt)
                    else:
                        for slug in missing:
                            results.append({"ticker": slug, "unit_price": None, "market": "crypto", "updated_at": None, "error": f"CMC error after {MAX_RETRIES} attempts"})
                else:
                    response.raise_for_status()

            except httpx.RequestError as e:
                logger.error("Request error in batch CMC on attempt %d: %s", attempt + 1, e)
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(2 ** attempt)
                else:
                    for slug in missing:
                        results.append({"ticker": slug, "unit_price": None, "market": "crypto", "updated_at": None, "error": str(e)})

    return results
