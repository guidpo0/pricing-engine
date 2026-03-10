import logging
from datetime import datetime, timezone
import httpx
import asyncio
from typing import Dict, Any, Optional

from app.config import settings

logger = logging.getLogger(__name__)

# Simple thread-safe in-memory cache
# Structure: { "ticker": {"price": float, "updated_at": datetime, "expires_at": float} }
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
    Fetch market quote for a given ticker from BRAPI or cache.
    Retries up to 3 times on 429 or 5xx errors with exponential backoff.
    """
    ticker = ticker.upper()
    cached_price = _get_from_cache(ticker)
    
    if cached_price is not None:
        logger.debug("Quote for %s found in cache", ticker)
        return {
            "price": cached_price,
            "updated_at": _quote_cache[ticker]["updated_at"]
        }

    url = f"{settings.brapi_base_url}/quote/{ticker}"
    params = {}
    if settings.brapi_token:
        params["token"] = settings.brapi_token

    async with httpx.AsyncClient(timeout=settings.http_timeout) as client:
        for attempt in range(MAX_RETRIES):
            try:
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
