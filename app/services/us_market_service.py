import logging
from datetime import datetime, timezone
import httpx
import asyncio
from typing import Dict, Any, Optional

from app.config import settings
from app.utils.database import add_ticker_us, get_all_tickers_us
from app.history.history_repository import history_repository

logger = logging.getLogger(__name__)

# Simple thread-safe in-memory cache
_quote_cache: Dict[str, Any] = {}
CACHE_TTL_SECONDS = 30 * 60  # 30 minutes
MAX_RETRIES = 3

def _get_from_cache(ticker: str) -> Optional[float]:
    """Retrieve quote from cache if available and not expired."""
    now = datetime.now(timezone.utc).timestamp()
    if ticker in _quote_cache:
        entry = _quote_cache[ticker]
        if now < entry["expires_at"]:
            return entry["price"]
    return None

def _get_fallback_cache(ticker: str) -> Optional[float]:
    """Retrieve quote from cache ignoring expiration (for 429 fallback)."""
    if ticker in _quote_cache:
        return _quote_cache[ticker]["price"]
    return None

def _set_in_cache(ticker: str, price: float) -> None:
    """Store quote in cache."""
    now = datetime.now(timezone.utc)
    _quote_cache[ticker] = {
        "price": price,
        "updated_at": now,
        "expires_at": now.timestamp() + CACHE_TTL_SECONDS
    }

async def get_us_market_quote(ticker: str) -> dict:
    """
    Fetch market quote for a US ticker from TwelveData or cache/database.
    On 429, logs warning and returns fallback from database (if available).
    On 5xx, retries up to 3 times with exponential backoff.
    Saves all quotes to PostgreSQL history.
    """
    ticker = ticker.upper()
    
    # Store ticker in the background DB
    add_ticker_us(ticker)
    
    # Try to get from in-memory cache first
    cached_price = _get_from_cache(ticker)
    
    if cached_price is not None:
        logger.debug("Quote for US ticker %s found in memory cache", ticker)
        return {
            "price": cached_price,
            "updated_at": _quote_cache[ticker]["updated_at"]
        }

    # Try to get from database (latest historical record)
    db_quote = history_repository.get_latest_us_stock_quote(ticker)
    if db_quote:
        logger.debug("Quote for US ticker %s found in database", ticker)
        _set_in_cache(ticker, float(db_quote["unit_price"]))
        return {
            "price": float(db_quote["unit_price"]),
            "updated_at": db_quote["recorded_at"]
        }

    url = f"{settings.twelve_data_base_url}/price"
    params = {"symbol": ticker, "apikey": settings.twelve_data_api_token}

    async with httpx.AsyncClient(timeout=settings.http_timeout) as client:
        for attempt in range(MAX_RETRIES):
            try:
                response = await client.get(url, params=params)
                
                # TwelveData often returns 200 with an error object for bad requests / rate limits
                data = response.json()
                
                if response.status_code == 200 and "price" in data:
                    price = float(data["price"])
                    _set_in_cache(ticker, price)
                    
                    # Save to PostgreSQL history
                    try:
                        history_repository.insert_us_stock_quote(ticker, price, "USD")
                    except Exception as e:
                        logger.warning("Failed to save US stock quote to database: %s", e)
                    
                    return {
                        "price": price,
                        "updated_at": _quote_cache[ticker]["updated_at"]
                    }
                elif response.status_code == 429 or (response.status_code == 200 and data.get("code") == 429):
                    logger.warning("Rate limit (429) hit for US ticker %s. Falling back to old cache.", ticker)
                    fallback = _get_fallback_cache(ticker)
                    if fallback is not None:
                        return {
                            "price": fallback,
                            "updated_at": _quote_cache[ticker]["updated_at"]
                        }
                    raise ValueError(f"Rate limit exceeded for {ticker} on first fetch (no cache available). Try again later.")
                
                elif response.status_code >= 500:
                    logger.warning("Attempt %d/%d failed for %s. Status %d. Retrying...", attempt + 1, MAX_RETRIES, ticker, response.status_code)
                    if attempt < MAX_RETRIES - 1:
                        await asyncio.sleep(2 ** attempt)
                    else:
                        raise ValueError(f"Failed to fetch quote for {ticker} after {MAX_RETRIES} attempts. Status: {response.status_code}")
                elif response.status_code == 404 or (response.status_code == 200 and data.get("status") == "error"):
                    raise ValueError(f"US Ticker {ticker} not found or invalid: {data.get('message', '')}")
                else:
                    response.raise_for_status()
                    
            except httpx.RequestError as e:
                logger.error("Request error for %s on attempt %d: %s", ticker, attempt + 1, e)
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(2 ** attempt)
                else:
                    raise ValueError(f"Network error fetching quote for US ticker {ticker}: {str(e)}") from e

    raise ValueError(f"Unexpected error fetching quote for US ticker {ticker}")
