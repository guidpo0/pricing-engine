"""
API routes for the Tesouro Direto pricing service.
"""
from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, status, Depends

from app.api.auth import verify_api_token
from app.models.bond import (
    BondPriceRequest,
    BondPriceResponse,
    BondType,
    PortfolioValueRequest,
    PortfolioValueResponse,
)
from app.models.cdb import CDBValueRequest, CDBValueResponse
from app.services import curve_service, inflation_service, cdb_service
from app.services.pricing_engine import calculate_pu
from app.services.cdb_pricing_engine import calculate_cdb
from app.models.lci_lca import LCILCAValueRequest, LCILCAValueResponse
from app.services.lci_lca_pricing_engine import calculate_lci_lca
from app.models.market import MarketQuoteResponse, TrackedTickersResponse, CurrencyHistoryResponse, CurrencyHistoryItem, BatchQuoteRequest, BatchQuoteResponse, BatchQuoteResult
from app.services import (
    market_service, us_market_service, crypto_market_service, currency_service
)
from app.utils.database import (
    get_all_tickers, get_all_tickers_us,
    get_all_crypto_slugs, get_all_currency_pairs
)
from app.history import history_repository

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
        ref = body.calculation_date or date.today()
        logger.info("Portfolio value bond_type=%s maturity=%s ref=%s body.calculation_date=%s quantity=%.4f",
                     body.bond_type, body.maturity_date, ref, body.calculation_date, body.quantity)
        result = calculate_pu(body.bond_type, body.maturity_date, spread=body.spread, ref=ref)
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
    "/market/cdi-factor",
    summary="Get accumulated CDI factor between two dates",
    tags=["Market Data"],
)
async def get_cdi_factor(
    start_date: str = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: str = Query(..., description="End date (YYYY-MM-DD)"),
    rate: float = Query(1.0, ge=0.0, description="CDI percentage multiplier (e.g. 1.0 = 100% CDI)"),
) -> dict:
    from datetime import date as date_type
    try:
        start = date_type.fromisoformat(start_date)
        end = date_type.fromisoformat(end_date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid date format: {exc}")

    if start >= end:
        raise HTTPException(status_code=400, detail="start_date must be before end_date")

    daily_factors = cdb_service.get_cdi_daily_factors()
    fallback_factor = cdb_service.get_fallback_daily_factor()

    factor = 1.0
    business_days = 0

    if not daily_factors:
        calendar_days = (end - start).days
        approx_bdays = int(calendar_days * 252 / 365)
        factor = (1 + fallback_factor * rate) ** approx_bdays
        business_days = approx_bdays
        logger.warning("CDI factor using fallback — no live BCB data")
    else:
        factor_by_date: dict[str, float] = {}
        for entry in daily_factors:
            factor_by_date[entry["data"]] = float(entry["valor"].replace(",", ".")) / 100.0

        available_dates = sorted(factor_by_date.keys())
        day, month, year = available_dates[0].split("/")
        earliest_available = date_type(int(year), int(month), int(day))

        if start < earliest_available:
            pre_days = (min(earliest_available, end) - start).days
            approx = int(pre_days * 252 / 365)
            factor *= (1 + fallback_factor * rate) ** approx
            business_days += approx

        for entry in daily_factors:
            d, m, y = entry["data"].split("/")
            entry_date = date_type(int(y), int(m), int(d))
            if entry_date <= start:
                continue
            if entry_date > end:
                break
            daily_factor = float(entry["valor"].replace(",", ".")) / 100.0
            factor *= (1 + daily_factor * rate)
            business_days += 1

    # Extract the reference CDI annual rate from the latest factor
    latest_factor = fallback_factor
    if daily_factors:
        last = float(daily_factors[-1]["valor"].replace(",", ".")) / 100.0
        latest_factor = last
    cdi_annual_rate = round((1 + latest_factor) ** 252 - 1, 6)

    return {
        "factor": round(factor, 10),
        "cdi_annual_rate": cdi_annual_rate,
        "business_days": business_days,
        "start_date": start_date,
        "end_date": end_date,
        "rate": rate,
    }


@router.get(
    "/market/quote/{ticker}",
    response_model=MarketQuoteResponse,
    summary="Get real-time market quote for a ticker (Ações/FIIs)",
    tags=["Market Data"],
)
async def get_market_quote(
    ticker: str,
    quantity: float | None = Query(None, description="Optional quantity for portfolio valuation"),
    date: str | None = Query(None, description="Optional date (YYYY-MM-DD) to get historical quote"),
) -> MarketQuoteResponse:
    """
    Get the real-time market quote for a Brazilian stock or real estate fund.
    First tries to get from database, if not available fetches from external API.
    
    If 'date' is provided, tries to get the quote for that specific date.
    If not found in database, fetches from external API and saves to database.
    """
    db_quote = None
    
    if date:
        db_quote = history_repository.get_stock_quote_by_date(ticker.upper(), date)
    
    if db_quote:
        quote_data = {
            "price": float(db_quote["unit_price"]),
            "updated_at": db_quote["recorded_at"]
        }
    elif date:
        try:
            quote_data = await market_service.get_market_quote_by_date(ticker, date)
            recorded_at = datetime.strptime(date, "%Y-%m-%d")
            history_repository.insert_stock_quote(ticker.upper(), quote_data["price"], "BRL", recorded_at=recorded_at)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND if "not found" in str(exc).lower() else status.HTTP_502_BAD_GATEWAY,
                detail={"error": "MARKET_DATA_ERROR", "detail": str(exc), "code": "MARKET_DATA_ERROR"},
            )
        except Exception as exc:
            logger.exception("Unexpected error fetching historical market quote for %s", ticker)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={"error": "INTERNAL_ERROR", "detail": "Unexpected error fetching historical quote.", "code": "INTERNAL_ERROR"},
            )
    else:
        db_quote = history_repository.get_latest_stock_quote(ticker.upper())
        if db_quote:
            quote_data = {
                "price": float(db_quote["unit_price"]),
                "updated_at": db_quote["recorded_at"]
            }
        else:
            try:
                quote_data = await market_service.get_market_quote(ticker)
                history_repository.insert_stock_quote(ticker.upper(), quote_data["price"], "BRL")
            except ValueError as exc:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND if "not found" in str(exc).lower() else status.HTTP_502_BAD_GATEWAY,
                    detail={"error": "MARKET_DATA_ERROR", "detail": str(exc), "code": "MARKET_DATA_ERROR"},
                )
            except Exception as exc:
                logger.exception("Unexpected error fetching market quote for %s", ticker)
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail={"error": "INTERNAL_ERROR", "detail": "Unexpected error fetching quote.", "code": "INTERNAL_ERROR"},
                )

    response = MarketQuoteResponse(
        ticker=ticker.upper(),
        unit_price=quote_data["price"],
        updated_at=quote_data["updated_at"],
    )

    if quantity is not None:
        response.quantity = quantity
        response.position_value = round(quote_data["price"] * quantity, 2)

    return response


@router.post(
    "/market/quotes/batch",
    response_model=BatchQuoteResponse,
    summary="Get real-time market quotes for multiple tickers in a single call",
    tags=["Market Data"],
)
async def get_batch_market_quotes(body: BatchQuoteRequest) -> BatchQuoteResponse:
    """
    Get real-time market quotes for multiple tickers across different markets (BR, US, crypto).
    For Brazilian tickers (Ações/FIIs), uses a single BRAPI call with comma-separated tickers.
    Results are cached in-memory and in the database for future requests.
    """
    raw = await market_service.get_batch_market_quotes(
        [t.dict() for t in body.tickers]
    )
    quotes = [
        BatchQuoteResult(
            ticker=r["ticker"],
            unit_price=r.get("unit_price"),
            market=r.get("market", "br"),
            updated_at=r.get("updated_at"),
            error=r.get("error"),
        )
        for r in raw
    ]
    return BatchQuoteResponse(quotes=quotes)

@router.get(
    "/market/quote/us/{ticker}",
    response_model=MarketQuoteResponse,
    summary="Get real-time market quote for a US ticker",
    tags=["Market Data"],
)
async def get_us_market_quote(
    ticker: str,
    quantity: float | None = Query(None, description="Optional quantity for portfolio valuation"),
    date: str | None = Query(None, description="Optional date (YYYY-MM-DD) to get historical quote"),
) -> MarketQuoteResponse:
    db_quote = None
    
    if date:
        db_quote = history_repository.get_us_stock_quote_by_date(ticker.upper(), date)
    
    if db_quote:
        quote_data = {
            "price": float(db_quote["unit_price"]),
            "updated_at": db_quote["recorded_at"]
        }
    elif date:
        try:
            quote_data = await us_market_service.get_us_market_quote_by_date(ticker, date)
            recorded_at = datetime.strptime(date, "%Y-%m-%d")
            history_repository.insert_us_stock_quote(ticker.upper(), quote_data["price"], "USD", recorded_at=recorded_at)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND if "not found" in str(exc).lower() else status.HTTP_502_BAD_GATEWAY,
                detail={"error": "MARKET_DATA_ERROR", "detail": str(exc), "code": "MARKET_DATA_ERROR"},
            ) from exc
        except Exception as exc:
            logger.exception("Unexpected error fetching historical US market quote for %s", ticker)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={"error": "INTERNAL_ERROR", "detail": "Unexpected error fetching historical quote.", "code": "INTERNAL_ERROR"},
            ) from exc
    else:
        db_quote = history_repository.get_latest_us_stock_quote(ticker.upper())
        if db_quote:
            quote_data = {
                "price": float(db_quote["unit_price"]),
                "updated_at": db_quote["recorded_at"]
            }
        else:
            try:
                quote_data = await us_market_service.get_us_market_quote(ticker)
                history_repository.insert_us_stock_quote(ticker.upper(), quote_data["price"], "USD")
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
    quantity: float | None = Query(None, description="Optional quantity for portfolio valuation"),
    date: str | None = Query(None, description="Optional date (YYYY-MM-DD) to get historical quote"),
) -> MarketQuoteResponse:
    db_quote = None
    
    if date:
        db_quote = history_repository.get_crypto_quote_by_date(slug.upper(), date)
    
    if db_quote:
        quote_data = {
            "price": float(db_quote["unit_price"]),
            "updated_at": db_quote["recorded_at"]
        }
    else:
        if date:
            logger.warning("No historical data found for crypto %s on %s. Using latest available quote.", slug, date)
        db_quote = history_repository.get_latest_crypto_quote(slug.upper())
        if db_quote:
            quote_data = {
                "price": float(db_quote["unit_price"]),
                "updated_at": db_quote["recorded_at"]
            }
        else:
            try:
                quote_data = await crypto_market_service.get_crypto_quote(slug)
                history_repository.insert_crypto_quote(slug.upper(), quote_data["price"], "USD")
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
    quantity: float | None = Query(None, description="Optional quantity to convert"),
    date: str | None = Query(None, description="Optional date (YYYY-MM-DD) for historical quote")
) -> MarketQuoteResponse:
    pair = f"{from_currency.upper()}-{to_currency.upper()}"
    
    if date:
        db_quote = history_repository.get_currency_quote_by_date(pair, date)
        
        if db_quote:
            quote_data = {
                "price": float(db_quote["unit_price"]),
                "updated_at": db_quote["recorded_at"]
            }
        else:
            try:
                quote_data = await currency_service.get_currency_quote_by_date(from_currency, to_currency, date)
                recorded_at = datetime.strptime(date, "%Y-%m-%d")
                history_repository.insert_currency_quote(pair, quote_data["price"], recorded_at=recorded_at)
            except ValueError as exc:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND if "not found" in str(exc).lower() else status.HTTP_502_BAD_GATEWAY,
                    detail={"error": "MARKET_DATA_ERROR", "detail": str(exc), "code": "MARKET_DATA_ERROR"},
                )
            except Exception as exc:
                logger.exception("Error fetching currency quote for %s-%s on %s", from_currency, to_currency, date)
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail={"error": "INTERNAL_ERROR", "detail": "Unexpected error fetching quote.", "code": "INTERNAL_ERROR"},
                )
    else:
        db_quote = history_repository.get_latest_currency_quote(pair)
        
        if db_quote:
            quote_data = {
                "price": float(db_quote["unit_price"]),
                "updated_at": db_quote["recorded_at"]
            }
        else:
            try:
                quote_data = await currency_service.get_currency_quote(from_currency, to_currency)
                history_repository.insert_currency_quote(pair, quote_data["price"])
            except ValueError as exc:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND if "not found" in str(exc).lower() else status.HTTP_502_BAD_GATEWAY,
                    detail={"error": "MARKET_DATA_ERROR", "detail": str(exc), "code": "MARKET_DATA_ERROR"},
                )
            except Exception as exc:
                logger.exception("Unexpected error fetching currency quote for %s-%s", from_currency, to_currency)
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail={"error": "INTERNAL_ERROR", "detail": "Unexpected error fetching quote.", "code": "INTERNAL_ERROR"},
                )

    response = MarketQuoteResponse(
        ticker=pair,
        unit_price=quote_data["price"],
        updated_at=quote_data["updated_at"],
    )

    if quantity is not None:
        response.quantity = quantity
        response.position_value = round(quote_data["price"] * quantity, 6)

    return response

# ---------------------------------------------------------------------------
# Currency history endpoint
# ---------------------------------------------------------------------------

@router.get(
    "/market/currency/history/{currency_pair}",
    response_model=CurrencyHistoryResponse,
    summary="Get historical exchange rate data for a currency pair",
    tags=["Market Data"],
)
async def get_currency_history(
    currency_pair: str,
    days: int = Query(30, ge=1, le=365, description="Number of days to retrieve")
) -> CurrencyHistoryResponse:
    """
    Get historical exchange rate data for a currency pair over the specified period.
    Returns daily quotes with calculated percentage changes between days.
    """
    pair = currency_pair.upper().replace("-", "-")
    
    history_data = history_repository.get_currency_history(pair, days)
    
    if not history_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "HISTORY_NOT_FOUND", "detail": f"No history found for currency pair {pair}", "code": "HISTORY_NOT_FOUND"},
        )
    
    history_items = []
    for i, record in enumerate(history_data):
        change = None
        if i > 0 and history_data[i-1].get("unit_price"):
            previous_price = float(history_data[i-1]["unit_price"])
            current_price = float(record["unit_price"])
            if previous_price > 0:
                change = round(((current_price - previous_price) / previous_price) * 100, 4)
        
        history_items.append(CurrencyHistoryItem(
            date=record["recorded_at"],
            price=float(record["unit_price"]),
            change=change
        ))
    
    variation_30_days = None
    if len(history_items) >= 2:
        first_price = history_items[-1].price
        last_price = history_items[0].price
        if first_price > 0:
            variation_30_days = round(((last_price - first_price) / first_price) * 100, 4)
    
    return CurrencyHistoryResponse(
        currency_pair=pair,
        history=history_items,
        variation_30_days=variation_30_days
    )

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
