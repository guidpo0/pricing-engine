import logging
from datetime import datetime, timezone
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

async def get_market_quote(ticker: str) -> dict:
    """
    Fetch market quote for a given ticker from BRAPI or cache/database.
    Retries up to 3 times on 429 or 5xx errors with exponential backoff.
    Saves all quotes to PostgreSQL history.
    """
    ticker = ticker.upper()
    
    # Store ticker in the background DB for future automatic refreshes
    add_ticker(ticker)
    
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
                    
                    # Save to PostgreSQL history
                    try:
                        history_repository.insert_stock_quote(ticker, price, "BRL")
                    except Exception as e:
                        logger.warning("Failed to save stock quote to database: %s", e)
                    
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
