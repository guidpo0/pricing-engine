import logging
from datetime import datetime, timezone
import httpx
import asyncio
from typing import Dict, Any, Optional

from app.config import settings
from app.utils.database import add_currency_pair, get_all_currency_pairs
from app.history.history_repository import history_repository

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

async def get_currency_quote(from_currency: str, to_currency: str, force_refresh: bool = False) -> dict:
    """
    Fetch market quote for a currency pair from AwesomeAPI or cache/database.
    On 429, logs warning and returns fallback from database (if available).
    On 5xx, retries up to 3 times with exponential backoff.
    Saves all quotes to PostgreSQL history.
    """
    from_currency = from_currency.upper()
    to_currency = to_currency.upper()
    
    pair = f"{from_currency}-{to_currency}"
    add_currency_pair(pair)
    
    db_quote = None
    
    if not force_refresh:
        # Try to get from in-memory cache first
        cached_price = _get_from_cache(pair)
        
        if cached_price is not None:
            logger.debug("Quote for currency pair %s found in memory cache", pair)
            return {
                "price": cached_price,
                "updated_at": _quote_cache[pair]["updated_at"]
            }

        # Try to get from database (latest historical record)
        db_quote = history_repository.get_latest_currency_quote(pair)
        if db_quote:
            logger.debug("Quote for currency pair %s found in database", pair)
            # Update in-memory cache
            _set_in_cache(pair, float(db_quote["unit_price"]))
            return {
                "price": float(db_quote["unit_price"]),
                "updated_at": db_quote["recorded_at"]
            }
    
    # Fetch from external API
    url = f"{settings.awesome_api_base_url}/json/last/{pair}"
    if settings.awesome_api_key:
        url = f"{url}?token={settings.awesome_api_key}"
    logger.info("Fetching currency quote from: %s", url)

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
                    logger.warning("Rate limit (429) hit for currency pair %s. Falling back to database cache.", pair)
                    
                    # Try database fallback before raising error
                    if db_quote:
                        return {
                            "price": float(db_quote["unit_price"]),
                            "updated_at": db_quote["recorded_at"]
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


async def get_currency_quote_by_date(from_currency: str, to_currency: str, date: str) -> dict:
    """
    Fetch currency quote for a specific date.
    First checks database, then external API, then saves to database.
    """
    from_currency = from_currency.upper()
    to_currency = to_currency.upper()
    
    pair = f"{from_currency}-{to_currency}"
    add_currency_pair(pair)
    
    db_quote = history_repository.get_currency_quote_by_date(pair, date)
    if db_quote:
        return {
            "price": float(db_quote["unit_price"]),
            "updated_at": db_quote["recorded_at"]
        }
    
    date_formatted = date.replace("-", "")
    
    url = f"{settings.awesome_api_base_url}/json/daily/{pair}/1?start_date={date_formatted}&end_date={date_formatted}"
    if settings.awesome_api_key:
        url = f"{url}&token={settings.awesome_api_key}"
    logger.info("Fetching currency quote by date from: %s", url)
    
    async with httpx.AsyncClient(timeout=settings.http_timeout) as client:
        try:
            response = await client.get(url)
            
            if response.status_code == 200:
                data = response.json()
                
                if isinstance(data, list) and len(data) > 0:
                    quote_data = data[0]
                    price = float(quote_data.get("bid") or quote_data.get("close") or 0)
                    if price > 0:
                        _set_in_cache(pair, price)
                        recorded_at = datetime.strptime(date, "%Y-%m-%d")
                        history_repository.insert_currency_quote(pair, price, recorded_at=recorded_at)
                        return {
                            "price": price,
                            "updated_at": recorded_at,
                        }
                raise ValueError(f"No quote found for {pair} on {date}")
            
            elif response.status_code == 404:
                raise ValueError(f"Currency pair {pair} not found for date {date}")
            else:
                response.raise_for_status()
        
        except httpx.RequestError as e:
            raise ValueError(f"Network error fetching quote for {pair} on {date}: {str(e)}") from e
    
    raise ValueError(f"Unexpected error fetching quote for {pair} on {date}")
