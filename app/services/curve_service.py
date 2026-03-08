"""
Yield curve service.

Fetches and caches the Pre (nominal) and IPCA+ (real) yield curves from ANBIMA,
and the SELIC target rate from BCB SGS series 11.

Provides linear interpolation for arbitrary tenors.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

CurveType = Literal["pre", "ipca", "selic"]

# ---------------------------------------------------------------------------
# Fallback curves (hardcoded as of early 2026 — refreshed by the scheduler)
# ---------------------------------------------------------------------------
_FALLBACK_PRE_CURVE: list[dict] = [
    {"tenor_years": 0.25, "rate": 0.1325},
    {"tenor_years": 0.5,  "rate": 0.1340},
    {"tenor_years": 1.0,  "rate": 0.1380},
    {"tenor_years": 2.0,  "rate": 0.1420},
    {"tenor_years": 3.0,  "rate": 0.1450},
    {"tenor_years": 5.0,  "rate": 0.1480},
    {"tenor_years": 7.0,  "rate": 0.1490},
    {"tenor_years": 10.0, "rate": 0.1500},
]

_FALLBACK_IPCA_CURVE: list[dict] = [
    {"tenor_years": 1.0,  "rate": 0.0750},
    {"tenor_years": 2.0,  "rate": 0.0780},
    {"tenor_years": 3.0,  "rate": 0.0790},
    {"tenor_years": 5.0,  "rate": 0.0800},
    {"tenor_years": 7.0,  "rate": 0.0820},
    {"tenor_years": 10.0, "rate": 0.0830},
    {"tenor_years": 15.0, "rate": 0.0840},
    {"tenor_years": 20.0, "rate": 0.0850},
]

_FALLBACK_SELIC_RATE: float = 0.1325  # 13.25% p.a.


@dataclass
class CurveCache:
    pre_curve: list[dict] = field(default_factory=lambda: list(_FALLBACK_PRE_CURVE))
    ipca_curve: list[dict] = field(default_factory=lambda: list(_FALLBACK_IPCA_CURVE))
    selic_rate: float = _FALLBACK_SELIC_RATE
    last_updated: datetime | None = None
    using_fallback: bool = True


# Module-level singleton cache
_cache = CurveCache()


def _linear_interpolate(curve: list[dict], tenor: float) -> float:
    """
    Linear interpolation (and flat extrapolation) over a tenor-rate curve.

    Args:
        curve: List of {"tenor_years": float, "rate": float} sorted ascending.
        tenor: Target tenor in years.

    Returns:
        Interpolated / extrapolated rate.
    """
    if not curve:
        raise ValueError("Yield curve is empty — cannot interpolate.")

    sorted_curve = sorted(curve, key=lambda p: p["tenor_years"])

    # Flat extrapolation at boundaries
    if tenor <= sorted_curve[0]["tenor_years"]:
        return sorted_curve[0]["rate"]
    if tenor >= sorted_curve[-1]["tenor_years"]:
        return sorted_curve[-1]["rate"]

    # Find bracketing points
    for i in range(len(sorted_curve) - 1):
        t0, r0 = sorted_curve[i]["tenor_years"], sorted_curve[i]["rate"]
        t1, r1 = sorted_curve[i + 1]["tenor_years"], sorted_curve[i + 1]["rate"]
        if t0 <= tenor <= t1:
            weight = (tenor - t0) / (t1 - t0)
            return r0 + weight * (r1 - r0)

    return sorted_curve[-1]["rate"]  # should not reach here


async def _fetch_selic_rate() -> float:
    """Fetch the current SELIC target rate from BCB SGS series 11."""
    url = f"{settings.bcb_sgs_base_url}.11/dados/ultimos/1?formato=json"
    async with httpx.AsyncClient(timeout=settings.http_timeout) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()
        # Rate is annualised daily SELIC — convert from % to decimal
        rate_pct = float(data[0]["valor"])
        return rate_pct / 100.0


async def _fetch_anbima_curves() -> tuple[list[dict], list[dict]]:
    """
    Attempt to fetch Pre and IPCA+ curves from ANBIMA.

    ANBIMA's public API requires institutional access in full. We use a best-effort
    approach against their public endpoints; on failure we fall back to the
    hardcoded curves.

    Returns:
        (pre_curve, ipca_curve) — each a list of {tenor_years, rate} dicts.
    """
    # ANBIMA public estimated term structure endpoint (CSV-like, public)
    # This endpoint returns tab-separated data for the last business day.
    url = "https://www.anbima.com.br/informacoes/est-termo/CZ-down.asp"
    pre_curve: list[dict] = []
    ipca_curve: list[dict] = []

    try:
        async with httpx.AsyncClient(
            timeout=settings.http_timeout,
            follow_redirects=True,
            headers={"User-Agent": "pricing-engine/1.0 (+https://github.com/guidpo0/pricing-engine)"},
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            text = resp.text

        # Parse ANBIMA CSV layout: rows are "YYYY-MM-DD\t<252du_vertex>\t<pre_rate>\t<ipca_rate>"
        # Vertices are in business days (252 basis), rates in % p.a.
        for line in text.splitlines():
            parts = line.strip().split("\t")
            if len(parts) < 4:
                continue
            try:
                du = int(parts[1])
                pre_rate = float(parts[2].replace(",", ".")) / 100.0
                ipca_rate = float(parts[3].replace(",", ".")) / 100.0
                tenor_years = du / 252.0
                pre_curve.append({"tenor_years": tenor_years, "rate": pre_rate})
                ipca_curve.append({"tenor_years": tenor_years, "rate": ipca_rate})
            except (ValueError, IndexError):
                continue

    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to fetch ANBIMA curves (%s). Using fallback.", exc)

    if not pre_curve:
        pre_curve = list(_FALLBACK_PRE_CURVE)
    if not ipca_curve:
        ipca_curve = list(_FALLBACK_IPCA_CURVE)

    return pre_curve, ipca_curve


async def refresh_curves() -> None:
    """Fetch fresh curve data and update the module-level cache."""
    global _cache  # noqa: PLW0603
    logger.info("Refreshing yield curves...")
    try:
        pre_curve, ipca_curve = await _fetch_anbima_curves()
        selic_rate = await _fetch_selic_rate()
        _cache = CurveCache(
            pre_curve=pre_curve,
            ipca_curve=ipca_curve,
            selic_rate=selic_rate,
            last_updated=datetime.utcnow(),
            using_fallback=False,
        )
        logger.info(
            "Curves refreshed. Pre points=%d, IPCA points=%d, SELIC=%.4f",
            len(pre_curve),
            len(ipca_curve),
            selic_rate,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Error refreshing curves: %s", exc)


def get_rate(tenor_years: float, curve_type: CurveType = "pre") -> float:
    """
    Get interpolated rate for a given tenor.

    Args:
        tenor_years: Time to maturity in years (252-day basis).
        curve_type: "pre" for nominal Pre curve, "ipca" for real IPCA+ curve.

    Returns:
        Interpolated rate as decimal.
    """
    if curve_type == "pre":
        return _linear_interpolate(_cache.pre_curve, tenor_years)
    elif curve_type == "ipca":
        return _linear_interpolate(_cache.ipca_curve, tenor_years)
    elif curve_type == "selic":
        return _cache.selic_rate
    else:
        raise ValueError(f"Unknown curve type: {curve_type!r}")


def get_selic_rate() -> float:
    """Return the cached SELIC target rate (decimal)."""
    return _cache.selic_rate


def get_cache_info() -> dict:
    """Return metadata about the current cache state (for debug endpoint)."""
    return {
        "last_updated": _cache.last_updated.isoformat() if _cache.last_updated else None,
        "using_fallback": _cache.using_fallback,
        "selic_rate": _cache.selic_rate,
        "pre_curve_points": len(_cache.pre_curve),
        "ipca_curve_points": len(_cache.ipca_curve),
        "pre_curve": _cache.pre_curve,
        "ipca_curve": _cache.ipca_curve,
    }
