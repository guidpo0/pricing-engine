"""
Yield curve service.

Fetches and caches the Pre (nominal) and IPCA+ (real) yield curves from ANBIMA,
and the SELIC target rate from BCB SGS series 11.

Provides linear interpolation for arbitrary tenors.
"""
from __future__ import annotations

import logging
from datetime import datetime, date
from typing import Literal

import httpx

from app.config import settings
from app.history.history_repository import history_repository

logger = logging.getLogger(__name__)

CurveType = Literal["pre", "ipca", "selic"]


def _linear_interpolate(curve: list[dict], tenor: float) -> float:
    if not curve:
        raise ValueError("Yield curve is empty — cannot interpolate.")

    sorted_curve = sorted(curve, key=lambda p: p["tenor_years"])

    if tenor <= sorted_curve[0]["tenor_years"]:
        return sorted_curve[0]["rate"]
    if tenor >= sorted_curve[-1]["tenor_years"]:
        return sorted_curve[-1]["rate"]

    for i in range(len(sorted_curve) - 1):
        t0, r0 = sorted_curve[i]["tenor_years"], sorted_curve[i]["rate"]
        t1, r1 = sorted_curve[i + 1]["tenor_years"], sorted_curve[i + 1]["rate"]
        if t0 <= tenor <= t1:
            weight = (tenor - t0) / (t1 - t0)
            return r0 + weight * (r1 - r0)

    return sorted_curve[-1]["rate"]


def get_latest_curve() -> dict:
    latest = history_repository.get_latest_curve()
    if latest is None:
        raise ValueError("No curve data in database. Run update-cache first.")
    return latest


async def _fetch_selic_rate() -> float:
    url = f"{settings.bcb_sgs_base_url}.11/dados/ultimos/1?formato=json"
    async with httpx.AsyncClient(timeout=settings.http_timeout) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()
        rate_pct = float(data[0]["valor"])
        return rate_pct / 100.0


async def _fetch_lft_vna() -> tuple[float, list[dict]]:
    from datetime import date as _date

    anchor_date = _date.fromisoformat(settings.lft_vna_anchor_date)
    today = _date.today()

    if today <= anchor_date:
        return settings.lft_vna_anchor, []

    start_str = anchor_date.strftime("%d/%m/%Y")
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

    vna = settings.lft_vna_anchor
    for entry in data:
        day, month, year = entry["data"].split("/")
        entry_date = _date(int(year), int(month), int(day))
        if entry_date <= anchor_date:
            continue
        daily_factor = float(entry["valor"].replace(",", ".")) / 100.0
        vna *= (1 + daily_factor)

    try:
        from app.history.selic_repository import upsert_selic_factors_batch
        upsert_selic_factors_batch(data, anchor_date)
    except Exception as exc:
        logger.warning("Failed to persist SELIC daily factors: %s", exc)

    return round(vna, 6), data


async def _fetch_anbima_curves() -> tuple[list[dict], list[dict]]:
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

        in_table = False
        for line in text.splitlines():
            parts = line.strip().split(";")
            if not in_table:
                if len(parts) >= 3 and parts[0] == "Vertices" and parts[1].startswith("ETTJ IPCA") and parts[2].startswith("ETTJ PREF"):
                    in_table = True
                continue

            if not parts or not parts[0]:
                break

            try:
                du_str = parts[0].replace(".", "")
                du = int(du_str)
                ipca_rate = float(parts[1].replace(",", ".")) / 100.0
                pre_rate = float(parts[2].replace(",", ".")) / 100.0

                tenor_years = du / 252.0
                pre_curve.append({"tenor_years": tenor_years, "rate": pre_rate})
                ipca_curve.append({"tenor_years": tenor_years, "rate": ipca_rate})
            except (ValueError, IndexError):
                continue

    except Exception as exc:
        logger.warning("Failed to fetch ANBIMA curves (%s).", exc)
        raise

    if not pre_curve or not ipca_curve:
        raise ValueError("Failed to fetch ANBIMA curves — no data returned.")

    return pre_curve, ipca_curve


async def refresh_curves() -> tuple[list[dict], list[dict], float, float, list[dict]]:
    logger.info("Refreshing yield curves...")
    pre_curve, ipca_curve = await _fetch_anbima_curves()
    selic_rate = await _fetch_selic_rate()
    lft_vna, lft_daily_factors = await _fetch_lft_vna()
    logger.info(
        "Curves refreshed. Pre points=%d, IPCA points=%d, SELIC=%.4f, LFT VNA=%.4f",
        len(pre_curve), len(ipca_curve), selic_rate, lft_vna,
    )
    return pre_curve, ipca_curve, selic_rate, lft_vna, lft_daily_factors


def get_rate(tenor_years: float, curve_type: CurveType = "pre") -> float:
    latest = get_latest_curve()

    if curve_type == "pre":
        return _linear_interpolate(latest["pre_curve"], tenor_years)
    elif curve_type == "ipca":
        return _linear_interpolate(latest["ipca_curve"], tenor_years)
    elif curve_type == "selic":
        return float(latest["selic_rate"])
    else:
        raise ValueError(f"Unknown curve type: {curve_type!r}")


def get_selic_rate() -> float:
    latest = get_latest_curve()
    return float(latest["selic_rate"])


def get_lft_vna() -> float:
    latest = get_latest_curve()
    return float(latest["lft_vna"])


def get_lft_vna_at(ref: date) -> float:
    from datetime import date as _date

    anchor_date = _date.fromisoformat(settings.lft_vna_anchor_date)

    if ref <= anchor_date:
        logger.info("get_lft_vna_at ref=%s <= anchor_date=%s returning anchor=%.4f", ref, anchor_date, settings.lft_vna_anchor)
        return settings.lft_vna_anchor

    vna = _compute_vna_from_db(ref, anchor_date)
    if vna is not None:
        return vna

    raise ValueError(f"No SELIC factors available to compute VNA for {ref}. Run update-cache first.")


def _compute_vna_from_db(ref: date, anchor_date: date) -> float | None:
    try:
        from app.history.selic_repository import get_selic_factors_up_to

        factors = get_selic_factors_up_to(ref)
        if not factors:
            return None

        vna = settings.lft_vna_anchor
        for entry in factors:
            vna *= (1 + entry["daily_factor"])

        result = round(vna, 6)
        logger.info("get_lft_vna_at ref=%s source=DB factors=%d vna=%.4f", ref, len(factors), result)
        return result
    except Exception as exc:
        logger.warning("Failed to compute VNA from DB: %s", exc)
        return None
