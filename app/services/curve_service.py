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
_FALLBACK_LFT_VNA: float = 18_503.43  # LFT VNA fallback (approximate, early March 2026)


@dataclass
class CurveCache:
    pre_curve: list[dict] = field(default_factory=lambda: list(_FALLBACK_PRE_CURVE))
    ipca_curve: list[dict] = field(default_factory=lambda: list(_FALLBACK_IPCA_CURVE))
    selic_rate: float = _FALLBACK_SELIC_RATE
    lft_vna: float = _FALLBACK_LFT_VNA
    lft_daily_factors: list[dict] = field(default_factory=list)
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


async def _fetch_lft_vna() -> tuple[float, list[dict]]:
    """
    Compute the current LFT (Tesouro Selic) VNA by projecting the anchor value
    stored in settings forward using recent daily SELIC factors (BCB SGS series 12).

    BCB SGS series 12 = SELIC accumulated daily factor (% a.d.).
    The LFT VNA starts at R$ 1,000 on 01/07/2000 and grows by this factor each
    business day. We anchor to a recently known VNA and accumulate only the
    incremental factors since that anchor date to avoid 25-year history downloads.

    Also persists the daily factors to the selic_daily_factors table so
    historical VNA values can be computed for any past reference date.

    Returns:
        (vna, daily_factors): VNA as of the latest available data, and the
        raw list of daily factor entries from BCB.
    """
    from datetime import date as _date

    anchor_date = _date.fromisoformat(settings.lft_vna_anchor_date)
    today = _date.today()

    if today <= anchor_date:
        return settings.lft_vna_anchor, []

    # Fetch daily factors from the day after anchor_date up to today
    start_str = (anchor_date.strftime("%d/%m/%Y"))
    end_str = today.strftime("%d/%m/%Y")
    url = (
        f"{settings.bcb_sgs_base_url}.12/dados"
        f"?dataInicial={start_str}&dataFinal={end_str}&formato=json"
    )
    async with httpx.AsyncClient(timeout=settings.http_timeout) as client:
        resp = await client.get(url)
        if resp.status_code == 404:
            return settings.lft_vna_anchor, []
        resp.raise_for_status()
        data = resp.json()

    # Compound anchor VNA with each business day factor AFTER the anchor date
    vna = settings.lft_vna_anchor
    for entry in data:
        day, month, year = entry["data"].split("/")
        entry_date = _date(int(year), int(month), int(day))
        if entry_date <= anchor_date:
            continue
        daily_factor = float(entry["valor"].replace(",", ".")) / 100.0
        vna *= (1 + daily_factor)

    # Persist factors to DB for historical queries
    try:
        from app.history.selic_repository import upsert_selic_factors_batch
        upsert_selic_factors_batch(data, anchor_date)
    except Exception as exc:
        logger.warning("Failed to persist SELIC daily factors: %s", exc)

    return round(vna, 6), data


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
    # This endpoint returns semicolon-separated data for the last business day,
    # containing multiple tables. We want the "ETTJ Inflação Implicita (IPCA)" table.
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

        # Parse ANBIMA CSV layout: search for the start of the data table
        # Header is: "Vertices;ETTJ IPCA;ETTJ PREF;Inflação Implícita"
        # Vertices are in business days (252 basis), rates in % p.a.
        in_table = False
        for line in text.splitlines():
            parts = line.strip().split(";")
            if not in_table:
                if len(parts) >= 3 and parts[0] == "Vertices" and parts[1].startswith("ETTJ IPCA") and parts[2].startswith("ETTJ PREF"):
                    in_table = True
                continue
            
            # End of table or empty line
            if not parts or not parts[0]:
                break
                
            try:
                # Format: 126;9,5301;13,9902;4,0720
                # Remove thousands separator (dot) if any, though usually only in >1000 vertices
                du_str = parts[0].replace(".", "")
                du = int(du_str)
                ipca_rate = float(parts[1].replace(",", ".")) / 100.0
                pre_rate = float(parts[2].replace(",", ".")) / 100.0
                
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
        lft_vna, lft_daily_factors = await _fetch_lft_vna()
        _cache = CurveCache(
            pre_curve=pre_curve,
            ipca_curve=ipca_curve,
            selic_rate=selic_rate,
            lft_vna=lft_vna,
            lft_daily_factors=lft_daily_factors,
            last_updated=datetime.utcnow(),
            using_fallback=False,
        )
        logger.info(
            "Curves refreshed. Pre points=%d, IPCA points=%d, SELIC=%.4f, LFT VNA=%.4f",
            len(pre_curve),
            len(ipca_curve),
            selic_rate,
            lft_vna,
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


def get_lft_vna() -> float:
    """Return the cached LFT VNA (Valor Nominal Atualizado pela SELIC acumulada)."""
    return _cache.lft_vna


def get_lft_vna_at(ref: date) -> float:
    """
    Compute the LFT VNA as of a specific reference date.

    Reads daily SELIC factors from the selic_daily_factors table (populated
    by the BCB fetch during refresh_curves). Falls back to the in-memory
    cache if the DB is not available.

    Args:
        ref: The reference (calculation) date.

    Returns:
        VNA as of the reference date, or the latest available VNA if the
        reference date is after all stored factors.
    """
    from datetime import date as _date

    anchor_date = _date.fromisoformat(settings.lft_vna_anchor_date)

    if ref <= anchor_date:
        logger.info("get_lft_vna_at ref=%s <= anchor_date=%s returning anchor=%.4f", ref, anchor_date, settings.lft_vna_anchor)
        return settings.lft_vna_anchor

    # Prefer DB-stored factors for historical computation
    db_vna = _compute_vna_from_db(ref, anchor_date)
    if db_vna is not None:
        return db_vna

    # Fallback: compute from in-memory cache
    logger.info("get_lft_vna_at ref=%s DB empty, using in-memory cache", ref)
    return _compute_vna_from_cache(ref, anchor_date)


def _compute_vna_from_db(ref: date, anchor_date: date) -> float | None:
    """Read SELIC factors from DB and compute VNA up to ref."""
    try:
        from app.history.selic_repository import get_selic_factors_up_to

        factors = get_selic_factors_up_to(ref)
        if not factors:
            return None

        vna = settings.lft_vna_anchor
        for entry in factors:
            vna *= (1 + entry["daily_factor"])

        result = round(vna, 6)
        logger.info(
            "get_lft_vna_at ref=%s source=DB factors=%d vna=%.4f cache_vna=%.4f",
            ref, len(factors), result, _cache.lft_vna,
        )
        return result
    except Exception as exc:
        logger.warning("Failed to compute VNA from DB: %s", exc)
        return None


def _compute_vna_from_cache(ref: date, anchor_date: date) -> float:
    """Fallback: compute VNA from in-memory _cache.lft_daily_factors."""
    if not _cache.lft_daily_factors:
        logger.info("get_lft_vna_at ref=%s no cached factors, returning latest vna=%.4f", ref, _cache.lft_vna)
        return _cache.lft_vna

    vna = settings.lft_vna_anchor
    sorted_entries = sorted(_cache.lft_daily_factors, key=lambda e: e["data"])
    factors_used = 0
    last_entry_date = anchor_date

    for entry in sorted_entries:
        day, month, year = entry["data"].split("/")
        entry_date = _date(int(year), int(month), int(day))
        if entry_date <= anchor_date:
            continue
        if entry_date > ref:
            break
        daily_factor = float(entry["valor"].replace(",", ".")) / 100.0
        vna *= (1 + daily_factor)
        factors_used += 1
        last_entry_date = entry_date

    logger.info(
        "get_lft_vna_at ref=%s source=cache anchor=%.4f factors_used=%d last_entry=%s vna=%.4f cache_vna=%.4f",
        ref, settings.lft_vna_anchor, factors_used, last_entry_date, round(vna, 6), _cache.lft_vna,
    )
    return round(vna, 6)


def get_cache_info() -> dict:
    """Return metadata about the current cache state (for debug endpoint)."""
    return {
        "last_updated": _cache.last_updated.isoformat() if _cache.last_updated else None,
        "using_fallback": _cache.using_fallback,
        "selic_rate": _cache.selic_rate,
        "lft_vna": _cache.lft_vna,
        "pre_curve_points": len(_cache.pre_curve),
        "ipca_curve_points": len(_cache.ipca_curve),
        "pre_curve": _cache.pre_curve,
        "ipca_curve": _cache.ipca_curve,
    }
