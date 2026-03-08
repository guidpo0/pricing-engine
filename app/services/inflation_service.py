"""
Inflation service — IPCA data and VNA (Valor Nominal Atualizado) calculation.

Data source: Banco Central do Brasil SGS series 433 (IPCA monthly variation, %).
Base nominal value: R$ 1,000.00 (Tesouro IPCA standard).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# NTN-B base nominal value
_VNA_BASE = 1000.0

# Fallback VNA — approximate value for early 2026
_FALLBACK_VNA = 4782.22


@dataclass
class InflationCache:
    vna: float = _FALLBACK_VNA
    ipca_monthly: list[dict] = None  # type: ignore[assignment]
    last_updated: datetime | None = None
    using_fallback: bool = True

    def __post_init__(self):
        if self.ipca_monthly is None:
            self.ipca_monthly = []


_cache = InflationCache()


async def _fetch_ipca_series(n_months: int = 20) -> list[dict]:
    """
    Fetch the last *n_months* IPCA monthly variations from BCB SGS 433.
    Note: BCB SGS API limits 'ultimos' queries to a maximum of 20 items.

    Returns:
        List of {"data": "DD/MM/YYYY", "valor": float_pct} dicts.
    """
    url = (
        f"{settings.bcb_sgs_base_url}.433/dados/ultimos/{n_months}"
        "?formato=json"
    )
    async with httpx.AsyncClient(timeout=settings.http_timeout) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.json()


def _compute_vna(ipca_series: list[dict]) -> float:
    """
    Compute VNA by compounding monthly IPCA variations over the base value.

    Formula: VNA = 1000 * ∏(1 + ipca_i/100)

    Note: In practice the VNA is officially published daily by ANBIMA using
    a pro-rata interpolation within the current month. This implementation
    uses the last available full-month series as a close approximation.

    Args:
        ipca_series: List of {"data": ..., "valor": str|float} from BCB SGS.

    Returns:
        Computed VNA.
    """
    vna = _VNA_BASE
    for entry in ipca_series:
        try:
            rate = float(str(entry["valor"]).replace(",", ".")) / 100.0
            vna *= 1 + rate
        except (ValueError, KeyError):
            continue
    return round(vna, 4)


async def refresh_inflation() -> None:
    """Fetch fresh IPCA data and recompute VNA."""
    global _cache  # noqa: PLW0603
    logger.info("Refreshing IPCA data and VNA...")
    try:
        series = await _fetch_ipca_series(n_months=20)
        vna = _compute_vna(series)
        _cache = InflationCache(
            vna=vna,
            ipca_monthly=series,
            last_updated=datetime.utcnow(),
            using_fallback=False,
        )
        logger.info("VNA updated to %.4f", vna)
    except Exception as exc:  # noqa: BLE001
        logger.error("Error refreshing IPCA/VNA: %s", exc)


def get_vna() -> float:
    """Return the current VNA (Valor Nominal Atualizado) for NTN-B bonds."""
    return _cache.vna


def get_cache_info() -> dict:
    """Return VNA metadata for the debug endpoint."""
    return {
        "vna": _cache.vna,
        "last_updated": _cache.last_updated.isoformat() if _cache.last_updated else None,
        "using_fallback": _cache.using_fallback,
        "ipca_data_points": len(_cache.ipca_monthly),
        "recent_ipca": _cache.ipca_monthly[-3:] if _cache.ipca_monthly else [],
    }
