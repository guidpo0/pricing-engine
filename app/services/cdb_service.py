"""
CDB market data service.

Fetches and caches the CDI daily factor (BCB SGS series 12) needed to
compute CDI-indexed CDB returns. IPCA data is reused from inflation_service.

CDI ≈ SELIC overnight — BCB series 12 is the official daily SELIC/CDI factor.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# Fallback: approximate CDI daily factor for 13.25% p.a.
# (1.1325)^(1/252) - 1 ≈ 0.049704% per business day
_FALLBACK_CDI_DAILY_FACTOR: float = 0.049704 / 100.0

# Max days of CDI history to cache. BCB SGS 12 /ultimos/ endpoint has no small
# limit. We fetch ~5 years (1260 business days) to cover the vast majority of
# open retail CDBs without needing the fallback calculation.
_CDI_FETCH_DAYS = 1260


@dataclass
class CDBRatesCache:
    """In-memory cache for CDI daily factors."""
    cdi_daily_factors: list[dict] = field(default_factory=list)
    last_updated: datetime | None = None
    using_fallback: bool = True


_cache = CDBRatesCache()


async def refresh_cdb_rates() -> None:
    """Fetch the latest CDI daily factors from BCB SGS series 12 and refresh cache."""
    global _cache  # noqa: PLW0603
    logger.info("Refreshing CDI daily factors...")
    try:
        url = f"{settings.bcb_sgs_base_url}.12/dados/ultimos/{_CDI_FETCH_DAYS}?formato=json"
        async with httpx.AsyncClient(timeout=settings.http_timeout) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
        _cache = CDBRatesCache(
            cdi_daily_factors=data,
            last_updated=datetime.utcnow(),
            using_fallback=False,
        )
        logger.info("CDI daily factors refreshed. Points=%d", len(data))
    except Exception as exc:  # noqa: BLE001
        logger.error("Error refreshing CDI factors: %s", exc)


def get_cdi_daily_factors() -> list[dict]:
    """Return cached CDI daily factors list."""
    return _cache.cdi_daily_factors


def get_fallback_daily_factor() -> float:
    """Return the hardcoded fallback CDI daily factor."""
    return _FALLBACK_CDI_DAILY_FACTOR


def get_cache_info() -> dict:
    """Return metadata about the CDI cache state."""
    return {
        "last_updated": _cache.last_updated.isoformat() if _cache.last_updated else None,
        "using_fallback": _cache.using_fallback,
        "cdi_data_points": len(_cache.cdi_daily_factors),
        "recent_factors": _cache.cdi_daily_factors[-3:] if _cache.cdi_daily_factors else [],
    }
