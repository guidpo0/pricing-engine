"""
API routes for the Tesouro Direto pricing service.
"""
from __future__ import annotations

import logging
from datetime import date
from enum import Enum
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, status, Depends
from fastapi.responses import HTMLResponse
import markdown

from app.api.auth import verify_api_token
from app.models.bond import (
    BondPriceRequest,
    BondPriceResponse,
    BondType,
    PortfolioValueRequest,
    PortfolioValueResponse,
)
from app.models.cdb import CDBValueRequest, CDBValueResponse
from app.services import curve_service, inflation_service
from app.services.pricing_engine import calculate_pu
from app.services.cdb_pricing_engine import calculate_cdb
from app.models.lci_lca import LCILCAValueRequest, LCILCAValueResponse
from app.services.lci_lca_pricing_engine import calculate_lci_lca
from app.models.market import MarketQuoteResponse, TrackedTickersResponse
from app.services import (
    market_service, us_market_service, crypto_market_service, currency_service
)
from app.utils.database import (
    get_all_tickers, get_all_tickers_us,
    get_all_crypto_slugs, get_all_currency_pairs
)

logger = logging.getLogger(__name__)

# Apply verify_api_token dependency to all routes in this router
router = APIRouter(dependencies=[Depends(verify_api_token)])

# ---------------------------------------------------------------------------
# Bond pricing endpoint
# ---------------------------------------------------------------------------


@router.post(
    "/bonds/price",
    response_model=BondPriceResponse,
    summary="Get mark-to-market price for a bond",
    tags=["Pricing"],
)
async def get_bond_price(body: BondPriceRequest) -> BondPriceResponse:
    """
    Calculate the Preço Unitário (PU) of a Tesouro Direto bond.

    Uses the current in-memory yield curve and VNA to produce a mark-to-market price.
    """
    try:
        result = calculate_pu(body.type, body.maturity_date, spread=body.spread)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "PRICING_ERROR", "detail": str(exc), "code": "PRICING_ERROR"},
        ) from exc
    except Exception as exc:
        logger.exception("Unexpected error pricing bond type=%s maturity=%s", body.type, body.maturity_date)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "INTERNAL_ERROR", "detail": "Unexpected pricing error.", "code": "INTERNAL_ERROR"},
        ) from exc

    return BondPriceResponse(
        bond_type=body.type,
        maturity_date=body.maturity_date,
        pu=result.pu,
        yield_rate=result.yield_rate,
        vna=result.vna,
        calculation_date=result.calculation_date,
    )


# ---------------------------------------------------------------------------
# Portfolio valuation endpoint
# ---------------------------------------------------------------------------

@router.post(
    "/portfolio/value",
    response_model=PortfolioValueResponse,
    summary="Calculate total position value for a bond holding",
    tags=["Portfolio"],
)
async def get_portfolio_value(body: PortfolioValueRequest) -> PortfolioValueResponse:
    """
    Calculate the total mark-to-market value of a Tesouro Direto position.

    `position_value = pu × quantity`
    """
    try:
        result = calculate_pu(body.bond_type, body.maturity_date, spread=body.spread)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "PRICING_ERROR", "detail": str(exc), "code": "PRICING_ERROR"},
        ) from exc
    except Exception as exc:
        logger.exception(
            "Unexpected error in portfolio valuation type=%s maturity=%s",
            body.bond_type, body.maturity_date,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "INTERNAL_ERROR", "detail": "Unexpected pricing error.", "code": "INTERNAL_ERROR"},
        ) from exc

    position_value = round(result.pu * body.quantity, 6)

    return PortfolioValueResponse(
        bond_type=body.bond_type,
        maturity_date=body.maturity_date,
        pu=result.pu,
        quantity=body.quantity,
        position_value=position_value,
        yield_rate=result.yield_rate,
        vna=result.vna,
        calculation_date=result.calculation_date,
    )


# ---------------------------------------------------------------------------
# Market data debug endpoints
# ---------------------------------------------------------------------------

@router.get(
    "/market/curves",
    summary="Inspect current in-memory yield curves",
    tags=["Market Data"],
)
async def get_market_curves() -> dict:
    """Return the currently cached Pre and IPCA+ yield curves plus SELIC rate."""
    return curve_service.get_cache_info()


@router.get(
    "/market/vna",
    summary="Inspect current VNA (Valor Nominal Atualizado)",
    tags=["Market Data"],
)
async def get_market_vna() -> dict:
    """Return the currently cached VNA for IPCA+ bonds."""
    return inflation_service.get_cache_info()


@router.get(
    "/market/tickers",
    response_model=TrackedTickersResponse,
    summary="Get all market tickers being tracked in the background",
    tags=["Market Data"],
)
async def get_tracked_tickers() -> TrackedTickersResponse:
    """Return the list of all tickers registered in the background fetching database."""
    br_tickers = get_all_tickers()
    us_tickers = get_all_tickers_us()
    crypto_slugs = get_all_crypto_slugs()
    currencies = get_all_currency_pairs()
    return TrackedTickersResponse(
        br_tickers=br_tickers,
        us_tickers=us_tickers,
        crypto_slugs=crypto_slugs,
        currencies=currencies,
    )


@router.get(
    "/market/quote/{ticker}",
    response_model=MarketQuoteResponse,
    summary="Get real-time market quote for a ticker (Ações/FIIs)",
    tags=["Market Data"],
)
async def get_market_quote(
    ticker: str,
    quantity: float | None = Query(None, description="Optional quantity for portfolio valuation")
) -> MarketQuoteResponse:
    """
    Get the real-time market quote for a Brazilian stock or real estate fund.
    Data is fetched from BRAPI and cached to avoid rate limits.
    """
    try:
        quote_data = await market_service.get_market_quote(ticker)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND if "not found" in str(exc).lower() else status.HTTP_502_BAD_GATEWAY,
            detail={"error": "MARKET_DATA_ERROR", "detail": str(exc), "code": "MARKET_DATA_ERROR"},
        ) from exc
    except Exception as exc:
        logger.exception("Unexpected error fetching market quote for %s", ticker)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "INTERNAL_ERROR", "detail": "Unexpected error fetching quote.", "code": "INTERNAL_ERROR"},
        ) from exc

    response = MarketQuoteResponse(
        ticker=ticker.upper(),
        unit_price=quote_data["price"],
        updated_at=quote_data["updated_at"],
    )

    if quantity is not None:
        response.quantity = quantity
        response.position_value = round(quote_data["price"] * quantity, 2)

    return response

@router.get(
    "/market/quote/us/{ticker}",
    response_model=MarketQuoteResponse,
    summary="Get real-time market quote for a US ticker",
    tags=["Market Data"],
)
async def get_us_market_quote(
    ticker: str,
    quantity: float | None = Query(None, description="Optional quantity for portfolio valuation")
) -> MarketQuoteResponse:
    try:
        quote_data = await us_market_service.get_us_market_quote(ticker)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND if "not found" in str(exc).lower() else status.HTTP_502_BAD_GATEWAY,
            detail={"error": "MARKET_DATA_ERROR", "detail": str(exc), "code": "MARKET_DATA_ERROR"},
        ) from exc
    except Exception as exc:
        logger.exception("Unexpected error fetching US market quote for %s", ticker)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "INTERNAL_ERROR", "detail": "Unexpected error fetching quote.", "code": "INTERNAL_ERROR"},
        ) from exc

    response = MarketQuoteResponse(
        ticker=ticker.upper(),
        unit_price=quote_data["price"],
        updated_at=quote_data["updated_at"],
    )

    if quantity is not None:
        response.quantity = quantity
        response.position_value = round(quote_data["price"] * quantity, 2)

    return response

@router.get(
    "/market/quote/crypto/{slug}",
    response_model=MarketQuoteResponse,
    summary="Get market quote for a cryptocurrency",
    tags=["Market Data"],
)
async def get_crypto_quote(
    slug: str,
    quantity: float | None = Query(None, description="Optional quantity for portfolio valuation")
) -> MarketQuoteResponse:
    try:
        quote_data = await crypto_market_service.get_crypto_quote(slug)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND if "not found" in str(exc).lower() else status.HTTP_502_BAD_GATEWAY,
            detail={"error": "MARKET_DATA_ERROR", "detail": str(exc), "code": "MARKET_DATA_ERROR"},
        ) from exc
    except Exception as exc:
        logger.exception("Unexpected error fetching crypto quote for %s", slug)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "INTERNAL_ERROR", "detail": "Unexpected error fetching quote.", "code": "INTERNAL_ERROR"},
        ) from exc

    response = MarketQuoteResponse(
        ticker=slug.upper(),
        unit_price=quote_data["price"],
        updated_at=quote_data["updated_at"],
    )

    if quantity is not None:
        response.quantity = quantity
        response.position_value = round(quote_data["price"] * quantity, 6)

    return response

@router.get(
    "/market/currency/{from_currency}/{to_currency}",
    response_model=MarketQuoteResponse,
    summary="Get market conversion rate between two currencies",
    tags=["Market Data"],
)
async def get_currency_quote(
    from_currency: str,
    to_currency: str,
    quantity: float | None = Query(None, description="Optional quantity to convert")
) -> MarketQuoteResponse:
    try:
        quote_data = await currency_service.get_currency_quote(from_currency, to_currency)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND if "not found" in str(exc).lower() else status.HTTP_502_BAD_GATEWAY,
            detail={"error": "MARKET_DATA_ERROR", "detail": str(exc), "code": "MARKET_DATA_ERROR"},
        ) from exc
    except Exception as exc:
        logger.exception("Unexpected error fetching currency quote for %s-%s", from_currency, to_currency)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "INTERNAL_ERROR", "detail": "Unexpected error fetching quote.", "code": "INTERNAL_ERROR"},
        ) from exc

    response = MarketQuoteResponse(
        ticker=f"{from_currency.upper()}-{to_currency.upper()}",
        unit_price=quote_data["price"],
        updated_at=quote_data["updated_at"],
    )

    if quantity is not None:
        response.quantity = quantity
        response.position_value = round(quote_data["price"] * quantity, 6)

    return response

# ---------------------------------------------------------------------------
# CDB pricing endpoint
# ---------------------------------------------------------------------------

@router.post(
    "/cdb/value",
    response_model=CDBValueResponse,
    summary="Calculate current mark-to-model value of a CDB investment",
    tags=["CDB"],
)
async def get_cdb_value(body: CDBValueRequest) -> CDBValueResponse:
    """
    Calculate the current mark-to-model value of a CDB investment.

    Supports three index types:
    - **CDI**: rate is the CDI percentage (e.g. `1.10` = 110% CDI)
    - **PREFIXADO**: rate is the fixed annual rate (e.g. `0.12` = 12% p.a.)
    - **IPCA**: rate is the real spread (e.g. `0.05` = IPCA + 5% p.a.)

    If the CDB has already matured, the response reflects the final accrued
    value at the maturity date.
    """
    try:
        result = calculate_cdb(body)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "PRICING_ERROR", "detail": str(exc), "code": "PRICING_ERROR"},
        ) from exc
    except Exception as exc:
        logger.exception(
            "Unexpected error pricing CDB index_type=%s principal=%.2f",
            body.index_type, body.principal,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "INTERNAL_ERROR", "detail": "Unexpected CDB pricing error.", "code": "INTERNAL_ERROR"},
        ) from exc

    return CDBValueResponse(
        index_type=body.index_type,
        principal=body.principal,
        rate=body.rate,
        purchase_date=body.purchase_date,
        maturity_date=body.maturity_date,
        current_value=result.current_value,
        yield_amount=result.yield_amount,
        yield_percentage=result.yield_percentage,
        is_matured=result.is_matured,
        calculation_date=result.calculation_date,
    )


# ---------------------------------------------------------------------------
# LCI/LCA pricing endpoint
# ---------------------------------------------------------------------------

@router.post(
    "/lci-lca/value",
    response_model=LCILCAValueResponse,
    summary="Calculate current mark-to-model value of an LCI or LCA investment",
    tags=["LCI/LCA"],
)
async def get_lci_lca_value(body: LCILCAValueRequest) -> LCILCAValueResponse:
    """
    Calculate the current mark-to-model value of an LCI or LCA investment.

    Supports three index types:
    - **CDI**: rate is the CDI percentage (e.g. `0.95` = 95% CDI)
    - **PREFIXADO**: rate is the fixed annual rate (e.g. `0.10` = 10% p.a.)
    - **IPCA**: rate is the real spread (e.g. `0.05` = IPCA + 5% p.a.)

    LCI and LCA are tax-exempt (IR = 0%).
    The response checks if `grace_period_days` (carência) has passed, setting `redeemable` to true/false.
    """
    try:
        result = calculate_lci_lca(body)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "PRICING_ERROR", "detail": str(exc), "code": "PRICING_ERROR"},
        ) from exc
    except Exception as exc:
        logger.exception(
            "Unexpected error pricing %s index_type=%s principal=%.2f",
            body.instrument_type, body.index_type, body.principal,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "INTERNAL_ERROR", "detail": f"Unexpected {body.instrument_type} pricing error.", "code": "INTERNAL_ERROR"},
        ) from exc

    return result

# ---------------------------------------------------------------------------
# Unprotected routes such as /health and /docs/readme are moved to main.py
# ---------------------------------------------------------------------------
