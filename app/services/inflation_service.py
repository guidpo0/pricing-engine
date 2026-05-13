"""
Inflation service — IPCA data and VNA (Valor Nominal Atualizado) calculation.

Data source: Banco Central do Brasil SGS series 433 (IPCA monthly variation, %).
Base nominal value: R$ 1,000.00 (Tesouro IPCA standard).
"""
from __future__ import annotations

import logging
from datetime import datetime

import httpx

from app.config import settings
from app.history.history_repository import history_repository

logger = logging.getLogger(__name__)

_VNA_BASE = 1000.0


async def _fetch_ipca_series(n_months: int = 20) -> list[dict]:
    url = (
        f"{settings.bcb_sgs_base_url}.433/dados/ultimos/{n_months}"
        "?formato=json"
    )
    async with httpx.AsyncClient(timeout=settings.http_timeout) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.json()


def _compute_vna(ipca_series: list[dict]) -> float:
    vna = _VNA_BASE
    for entry in ipca_series:
        try:
            rate = float(str(entry["valor"]).replace(",", ".")) / 100.0
            vna *= 1 + rate
        except (ValueError, KeyError):
            continue
    return round(vna, 4)


async def refresh_inflation() -> tuple[float, list[dict]]:
    logger.info("Refreshing IPCA data and VNA...")
    series = await _fetch_ipca_series(n_months=20)
    vna = _compute_vna(series)
    logger.info("VNA updated to %.4f", vna)
    return vna, series


def get_vna() -> float:
    latest = history_repository.get_latest_inflation()
    if latest is None:
        raise ValueError("No inflation data in database. Run update-cache first.")
    return float(latest["vna"])
