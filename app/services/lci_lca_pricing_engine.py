"""
LCI/LCA pricing engine.

Implements mark-to-model valuation for LCI and LCA instruments, which are
exempt from income tax (IR). They share the same index types as CDBs but
incorporate a grace period (carência).

All functions are pure (no I/O, no side-effects); market data is injected
via the cdb_service and inflation_service caches (re-using CDB and generic rate logic).
"""
from __future__ import annotations

import logging
from datetime import date

from app.models.lci_lca import LCILCAIndexType, LCILCAValueRequest, LCILCAValueResponse

# We reuse the mathematical core of CDB pricing, since the gross accumulation logic
# (CDI compounded daily, IPCA + spread, or Prefixado) is identical for LCI/LCA.
# Because LCI/LCA are tax-exempt, their gross value *is* their net value.
from app.services.cdb_pricing_engine import price_cdb_cdi, price_cdb_prefixado, price_cdb_ipca

logger = logging.getLogger(__name__)


def calculate_lci_lca(request: LCILCAValueRequest, ref: date | None = None) -> LCILCAValueResponse:
    """
    Dispatch LCI/LCA pricing to the correct formula based on index type.

    The valuation date is capped at maturity_date.
    The response checks if the instrument is redeemable.

    Args:
        request: Validated LCI/LCA value request.
        ref:     Valuation date (defaults to today).

    Returns:
        LCILCAValueResponse with the mark-to-model value and redeemability status.
    """
    ref = ref or date.today()

    # Cap ref at maturity
    effective_ref = min(ref, request.maturity_date)
    
    logger.debug(
        "Pricing %s type=%s principal=%.2f rate=%.4f purchase=%s maturity=%s ref=%s",
        request.instrument_type, request.index_type, request.principal, request.rate,
        request.purchase_date, request.maturity_date, effective_ref,
    )

    match request.index_type:
        case LCILCAIndexType.CDI:
            result = price_cdb_cdi(request.principal, request.rate, request.purchase_date, effective_ref)
        case LCILCAIndexType.PREFIXADO:
            result = price_cdb_prefixado(request.principal, request.rate, request.purchase_date, effective_ref)
        case LCILCAIndexType.IPCA:
            result = price_cdb_ipca(request.principal, request.rate, request.purchase_date, effective_ref)
        case _:
            raise ValueError(f"Unsupported LCI/LCA index type: {request.index_type!r}")

    # Check grace period (carência)
    days_since_purchase = (ref - request.purchase_date).days
    redeemable = days_since_purchase >= request.grace_period_days

    return LCILCAValueResponse(
        instrument_type=request.instrument_type,
        current_value=result.current_value,
        yield_amount=result.yield_amount,
        yield_percentage=result.yield_percentage,
        redeemable=redeemable,
        calculation_date=ref,
    )
