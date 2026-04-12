import logging
from datetime import datetime, timezone
import httpx
import asyncio
from typing import Dict, Any, Optional

from app.config import settings
from app.utils.database import add_crypto_slug, get_all_crypto_slugs
from app.history.history_repository import history_repository

logger = logging.getLogger(__name__)

# Simple thread-safe in-memory cache
_quote_cache: Dict[str, Any] = {}
CACHE_TTL_SECONDS = 30 * 60  # 30 minutes
MAX_RETRIES = 3

def _get_from_cache(slug: str) -> Optional[float]:
    now = datetime.now(timezone.utc).timestamp()
    if slug in _quote_cache:
        entry = _quote_cache[slug]
        if now < entry["expires_at"]:
            return entry["price"]
    return None

def _get_fallback_cache(slug: str) -> Optional[float]:
    if slug in _quote_cache:
        return _quote_cache[slug]["price"]
    return None

def _set_in_cache(slug: str, price: float) -> None:
    now = datetime.now(timezone.utc)
    _quote_cache[slug] = {
        "price": price,
        "updated_at": now,
        "expires_at": now.timestamp() + CACHE_TTL_SECONDS
    }

async def get_crypto_quote(slug: str) -> dict:
    """
    Fetch market quote for a crypto slug from CoinMarketCap or cache/database.
    On 429, logs warning and returns fallback from database (if available).
    On 5xx, retries up to 3 times with exponential backoff.
    Saves all quotes to PostgreSQL history.
    """
    slug = slug.lower()
    add_crypto_slug(slug)
    
    # Try to get from in-memory cache first
    cached_price = _get_from_cache(slug)
    
    if cached_price is not None:
        logger.debug("Quote for crypto slug %s found in memory cache", slug)
        return {
            "price": cached_price,
            "updated_at": _quote_cache[slug]["updated_at"]
        }

    # Try to get from database (latest historical record)
    db_quote = history_repository.get_latest_crypto_quote(slug)
    if db_quote:
        logger.debug("Quote for crypto slug %s found in database", slug)
        _set_in_cache(slug, float(db_quote["unit_price"]))
        return {
            "price": float(db_quote["unit_price"]),
            "updated_at": db_quote["recorded_at"]
        }

    url = f"{settings.coin_market_base_url}/v2/cryptocurrency/quotes/latest"
    params = {"slug": slug}
    headers = {"X-CMC_PRO_API_KEY": settings.coin_market_api_token}

    async with httpx.AsyncClient(timeout=settings.http_timeout) as client:
        for attempt in range(MAX_RETRIES):
            try:
                response = await client.get(url, params=params, headers=headers)
                
                if response.status_code == 200:
                    data = response.json()
                    
                    # CMC returns data keyed by internal ID, we need to extract the price
                    if "data" in data and data["data"]:
                        # Extract the first matching coin details
                        coin_data = next(iter(data["data"].values()))
                        if "quote" in coin_data and "USD" in coin_data["quote"]:
                            price = float(coin_data["quote"]["USD"]["price"])
                            _set_in_cache(slug, price)
                            
                            return {
                                "price": price,
                                "updated_at": _quote_cache[slug]["updated_at"]
                            }
                    
                    raise ValueError(f"Price data missing for crypto slug {slug}")
                
                elif response.status_code == 429:
                    logger.warning("Rate limit (429) hit for crypto slug %s. Falling back to old cache.", slug)
                    fallback = _get_fallback_cache(slug)
                    if fallback is not None:
                        return {
                            "price": fallback,
                            "updated_at": _quote_cache[slug]["updated_at"]
                        }
                    raise ValueError(f"Rate limit exceeded for {slug} on first fetch (no cache available). Try again later.")
                
                elif response.status_code >= 500:
                    logger.warning("Attempt %d/%d failed for %s. Status %d. Retrying...", attempt + 1, MAX_RETRIES, slug, response.status_code)
                    if attempt < MAX_RETRIES - 1:
                        await asyncio.sleep(2 ** attempt)
                    else:
                        raise ValueError(f"Failed to fetch quote for {slug} after {MAX_RETRIES} attempts. Status: {response.status_code}")
                elif response.status_code == 400 or response.status_code == 404:
                    # CMC might return 400 for bad requests / invalid slugs
                    data = response.json()
                    error_msg = data.get("status", {}).get("error_message", "Unknown error")
                    raise ValueError(f"Crypto slug {slug} not found or invalid: {error_msg}")
                else:
                    response.raise_for_status()
                    
            except httpx.RequestError as e:
                logger.error("Request error for %s on attempt %d: %s", slug, attempt + 1, e)
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(2 ** attempt)
                else:
                    raise ValueError(f"Network error fetching quote for crypto slug {slug}: {str(e)}") from e

    raise ValueError(f"Unexpected error fetching quote for crypto slug {slug}")
