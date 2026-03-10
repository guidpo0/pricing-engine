import logging
from datetime import datetime, timezone
import httpx
import asyncio
from typing import Dict, Any, Optional

from app.config import settings
from app.utils.database import add_currency_pair, get_all_currency_pairs

logger = logging.getLogger(__name__)

# Simple thread-safe in-memory cache
_quote_cache: Dict[str, Any] = {}
CACHE_TTL_SECONDS = 30 * 60  # 30 minutes
MAX_RETRIES = 3

def _get_from_cache(pair: str) -> Optional[float]:
    now = datetime.now(timezone.utc).timestamp()
    if pair in _quote_cache:
        entry = _quote_cache[pair]
        if now < entry["expires_at"]:
            return entry["price"]
    return None

def _get_fallback_cache(pair: str) -> Optional[float]:
    if pair in _quote_cache:
        return _quote_cache[pair]["price"]
    return None

def _set_in_cache(pair: str, price: float) -> None:
    now = datetime.now(timezone.utc)
    _quote_cache[pair] = {
        "price": price,
        "updated_at": now,
        "expires_at": now.timestamp() + CACHE_TTL_SECONDS
    }

async def get_currency_quote(from_currency: str, to_currency: str) -> dict:
    """
    Fetch market quote for a currency pair from AwesomeAPI or cache.
    On 429, logs warning and returns fallback cache (if available).
    On 5xx, retries up to 3 times with exponential backoff.
    """
    from_currency = from_currency.upper()
    to_currency = to_currency.upper()
    
    pair = f"{from_currency}-{to_currency}"
    add_currency_pair(pair)
    
    cached_price = _get_from_cache(pair)
    
    if cached_price is not None:
        logger.debug("Quote for currency pair %s found in cache", pair)
        return {
            "price": cached_price,
            "updated_at": _quote_cache[pair]["updated_at"]
        }

    # AwesomeAPI uses exactly the USD-BRL format in the URL
    url = f"{settings.awesome_api_base_url}/last/{pair}"

    async with httpx.AsyncClient(timeout=settings.http_timeout) as client:
        for attempt in range(MAX_RETRIES):
            try:
                response = await client.get(url)
                
                if response.status_code == 200:
                    data = response.json()
                    
                    # AwesomeAPI returns data keyed by the pair symbol without hyphen (USDBRL)
                    dict_key = f"{from_currency}{to_currency}"
                    
                    if dict_key in data and "bid" in data[dict_key]:
                        price = float(data[dict_key]["bid"])
                        _set_in_cache(pair, price)
                        return {
                            "price": price,
                            "updated_at": _quote_cache[pair]["updated_at"]
                        }
                    
                    raise ValueError(f"Price data missing for currency pair {pair}")
                
                elif response.status_code == 404:
                    raise ValueError(f"Currency pair {pair} not found on AwesomeAPI")
                
                elif response.status_code == 429:
                    logger.warning("Rate limit (429) hit for currency pair %s. Falling back to old cache.", pair)
                    fallback = _get_fallback_cache(pair)
                    if fallback is not None:
                        return {
                            "price": fallback,
                            "updated_at": _quote_cache[pair]["updated_at"]
                        }
                    raise ValueError(f"Rate limit exceeded for {pair} on first fetch (no cache available). Try again later.")
                
                elif response.status_code >= 500:
                    logger.warning("Attempt %d/%d failed for %s. Status %d. Retrying...", attempt + 1, MAX_RETRIES, pair, response.status_code)
                    if attempt < MAX_RETRIES - 1:
                        await asyncio.sleep(2 ** attempt)
                    else:
                        raise ValueError(f"Failed to fetch quote for {pair} after {MAX_RETRIES} attempts. Status: {response.status_code}")
                else:
                    response.raise_for_status()
                    
            except httpx.RequestError as e:
                logger.error("Request error for %s on attempt %d: %s", pair, attempt + 1, e)
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(2 ** attempt)
                else:
                    raise ValueError(f"Network error fetching quote for currency pair {pair}: {str(e)}") from e

    raise ValueError(f"Unexpected error fetching quote for currency pair {pair}")
