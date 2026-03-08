"""
CDB (Certificado de Depósito Bancário) pricing engine.

Implements mark-to-model valuation for the three main CDB yield structures
available in the Brazilian retail market:

  1. CDI indexed — yield grows with the daily CDI factor × percentage
  2. Prefixado   — simple compound interest at a fixed annual rate
  3. IPCA indexed — inflation adjusted return with a real spread

All functions are pure (no I/O, no side-effects); market data is injected
via the cdb_service and inflation_service caches.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import NamedTuple

from app.models.cdb import CDBIndexType, CDBValueRequest
from app.services import cdb_service, inflation_service

logger = logging.getLogger(__name__)


class CDBResult(NamedTuple):
    current_value: float
    yield_amount: float
    yield_percentage: float
    is_matured: bool
    calculation_date: date


# ---------------------------------------------------------------------------
# CDI Indexed
# ---------------------------------------------------------------------------

def price_cdb_cdi(
    principal: float,
    rate: float,
    purchase_date: date,
    ref: date | None = None,
) -> CDBResult:
    """
    Value a CDI-indexed CDB.

    Growth follows the accumulated CDI factor (BCB SGS series 12) multiplied
    daily by the contracted percentage.

    Formula (daily compounding):
        value = principal * Π (1 + daily_cdi_factor * rate)
        for each business day from purchase_date to ref.

    Args:
        principal:     Initial investment in BRL.
        rate:          CDI percentage (e.g. 1.10 for 110% CDI).
        purchase_date: Purchase date.
        ref:           Valuation date (defaults to today).

    Returns:
        CDBResult with the current mark-to-model value.
    """
    ref = ref or date.today()
    is_matured = ref >= date.today()  # will be set more precisely by caller

    daily_factors = cdb_service.get_cdi_daily_factors()
    fallback_factor = cdb_service.get_fallback_daily_factor()

    if not daily_factors:
        # No live data — use fallback constant and estimate with calendar days
        calendar_days = (ref - purchase_date).days
        # Approximate business days: calendar_days * (252/365)
        approx_bdays = int(calendar_days * 252 / 365)
        value = principal * ((1 + fallback_factor * rate) ** approx_bdays)
        logger.warning("CDI pricing using fallback factor — no live BCB data available")
    else:
        # Use real daily factors for days we have data; extrapolate older days
        # Build a lookup of available factors by date string
        factor_by_date: dict[str, float] = {}
        for entry in daily_factors:
            factor_by_date[entry["data"]] = float(entry["valor"].replace(",", ".")) / 100.0

        # Earliest date in cache
        available_dates = sorted(factor_by_date.keys())
        earliest_available = _parse_bcb_date(available_dates[0])

        value = principal

        # Phase 1: days before the cache window — use fallback factor
        if purchase_date < earliest_available:
            pre_cache_days = (min(earliest_available, ref) - purchase_date).days
            approx_bdays = int(pre_cache_days * 252 / 365)
            value *= (1 + fallback_factor * rate) ** approx_bdays

        # Phase 2: days within the cache window
        for entry in daily_factors:
            entry_date = _parse_bcb_date(entry["data"])
            if entry_date <= purchase_date:
                continue
            if entry_date > ref:
                break
            daily_factor = float(entry["valor"].replace(",", ".")) / 100.0
            value *= (1 + daily_factor * rate)

    current_value = round(value, 2)
    yield_amount = round(current_value - principal, 2)
    yield_percentage = round((yield_amount / principal) * 100, 4)

    return CDBResult(
        current_value=current_value,
        yield_amount=yield_amount,
        yield_percentage=yield_percentage,
        is_matured=ref >= date.today(),
        calculation_date=ref,
    )


# ---------------------------------------------------------------------------
# Prefixado (Fixed Rate)
# ---------------------------------------------------------------------------

def price_cdb_prefixado(
    principal: float,
    rate: float,
    purchase_date: date,
    ref: date | None = None,
) -> CDBResult:
    """
    Value a fixed-rate (Prefixado) CDB.

    Formula:
        years   = (ref - purchase_date).days / 365.0
        value   = principal * (1 + rate) ^ years

    Args:
        principal:     Initial investment in BRL.
        rate:          Annual interest rate as a decimal (e.g. 0.12 = 12% p.a.).
        purchase_date: Purchase date.
        ref:           Valuation date (defaults to today).

    Returns:
        CDBResult with the current mark-to-model value.
    """
    ref = ref or date.today()
    years = (ref - purchase_date).days / 365.0
    value = principal * (1 + rate) ** years

    current_value = round(value, 2)
    yield_amount = round(current_value - principal, 2)
    yield_percentage = round((yield_amount / principal) * 100, 4)

    return CDBResult(
        current_value=current_value,
        yield_amount=yield_amount,
        yield_percentage=yield_percentage,
        is_matured=ref >= date.today(),
        calculation_date=ref,
    )


# ---------------------------------------------------------------------------
# IPCA Indexed
# ---------------------------------------------------------------------------

def price_cdb_ipca(
    principal: float,
    rate: float,
    purchase_date: date,
    ref: date | None = None,
) -> CDBResult:
    """
    Value an IPCA-indexed CDB.

    Formula:
        inflation_factor = Π (1 + monthly_ipca_i / 100)
                           for each full IPCA month since purchase_date
        years            = (ref - purchase_date).days / 365.0
        value            = principal * inflation_factor * (1 + rate) ^ years

    Args:
        principal:     Initial investment in BRL.
        rate:          Real spread rate as a decimal (e.g. 0.05 = IPCA + 5% p.a.).
        purchase_date: Purchase date.
        ref:           Valuation date (defaults to today).

    Returns:
        CDBResult with the current mark-to-model value.
    """
    ref = ref or date.today()

    # Retrieve IPCA monthly series from the existing inflation cache
    cache_info = inflation_service.get_cache_info()
    ipca_series = cache_info.get("recent_ipca") or []

    # Try to build a fuller series; fall back to whatever is available
    # (The inflation service stores the last 20 months from BCB SGS 433)
    full_series: list[dict] = []
    try:
        full_series = inflation_service._cache.ipca_monthly  # type: ignore[attr-defined]
    except AttributeError:
        full_series = ipca_series

    # Compute accumulated inflation since purchase_date
    inflation_factor = 1.0
    for entry in full_series:
        try:
            # BCB date format: "DD/MM/YYYY"
            day, month, year = entry["data"].split("/")
            entry_date = date(int(year), int(month), int(day))
        except (KeyError, ValueError):
            continue

        # Include months that started on or after purchase_date month
        entry_month_start = date(entry_date.year, entry_date.month, 1)
        purchase_month_start = date(purchase_date.year, purchase_date.month, 1)

        if entry_month_start < purchase_month_start:
            continue
        if entry_date > ref:
            break

        monthly_rate = float(str(entry["valor"]).replace(",", ".")) / 100.0
        inflation_factor *= (1 + monthly_rate)

    years = (ref - purchase_date).days / 365.0
    value = principal * inflation_factor * (1 + rate) ** years

    current_value = round(value, 2)
    yield_amount = round(current_value - principal, 2)
    yield_percentage = round((yield_amount / principal) * 100, 4)

    return CDBResult(
        current_value=current_value,
        yield_amount=yield_amount,
        yield_percentage=yield_percentage,
        is_matured=ref >= date.today(),
        calculation_date=ref,
    )


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

def calculate_cdb(request: CDBValueRequest, ref: date | None = None) -> CDBResult:
    """
    Dispatch CDB pricing to the correct formula based on index type.

    The valuation date is capped at maturity_date so a post-maturity request
    returns the final accrued value (as the investment stopped growing at expiry).

    Args:
        request: Validated CDB value request.
        ref:     Valuation date (defaults to today).

    Returns:
        CDBResult with the mark-to-model value.
    """
    ref = ref or date.today()

    # Cap ref at maturity — CDB stops accruing after maturity
    is_matured = ref > request.maturity_date
    effective_ref = min(ref, request.maturity_date)

    logger.debug(
        "Pricing CDB type=%s principal=%.2f rate=%.4f purchase=%s maturity=%s ref=%s",
        request.index_type, request.principal, request.rate,
        request.purchase_date, request.maturity_date, effective_ref,
    )

    match request.index_type:
        case CDBIndexType.CDI:
            result = price_cdb_cdi(request.principal, request.rate, request.purchase_date, effective_ref)
        case CDBIndexType.PREFIXADO:
            result = price_cdb_prefixado(request.principal, request.rate, request.purchase_date, effective_ref)
        case CDBIndexType.IPCA:
            result = price_cdb_ipca(request.principal, request.rate, request.purchase_date, effective_ref)
        case _:
            raise ValueError(f"Unsupported CDB index type: {request.index_type!r}")

    # Override is_matured flag with the real comparison
    return CDBResult(
        current_value=result.current_value,
        yield_amount=result.yield_amount,
        yield_percentage=result.yield_percentage,
        is_matured=is_matured,
        calculation_date=ref,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_bcb_date(date_str: str) -> date:
    """Parse a BCB date string 'DD/MM/YYYY' into a date object."""
    day, month, year = date_str.split("/")
    return date(int(year), int(month), int(day))
