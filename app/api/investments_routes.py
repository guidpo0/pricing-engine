"""
API routes for investment history management.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query, status, Depends

from app.models.market import MarketQuoteResponse, TrackedTickersResponse
from app.api.auth import verify_api_token
from app.services import (
    market_service, us_market_service, crypto_market_service,
    currency_service
)
from app.services.investment_service import (
    update_all_cache
)
from app.utils.database import (
    get_all_tickers, get_all_tickers_us,
    get_all_crypto_slugs, get_all_currency_pairs
)
from app.history import history_repository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/investments", tags=["Investments"], dependencies=[Depends(verify_api_token)])


@router.post(
    "/update-cache",
    summary="Update investment data history",
    tags=["Investments"],
)
async def update_cache():
    """
    Atualiza o histórico persistente de dados de investimentos.
    
    Este endpoint deve ser chamado por um cron job externo (GitHub Actions)
    para atualizar os dados de investimentos periodicamente.
    
    O endpoint:
    - Consulta as APIs externas de investimento
    - Salva os resultados no banco PostgreSQL (INSERT only, nunca UPDATE/DELETE)
    
    O endpoint é idempotente - pode ser chamado várias vezes ao dia.
    """
    try:
        result = await update_all_cache()
        return result
    except Exception as exc:
        logger.exception("Failed to update history")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "HISTORY_UPDATE_ERROR", "detail": str(exc), "code": "HISTORY_UPDATE_ERROR"},
        )


@router.get(
    "/cache-info",
    summary="Get cache information",
    tags=["Investments"],
)
async def get_cache_information():
    """Retorna informações sobre os dados mais recentes no banco."""
    latest_curve = history_repository.get_latest_curve()
    latest_inflation = history_repository.get_latest_inflation()
    return {
        "curves_last_updated": latest_curve["recorded_at"] if latest_curve else None,
        "inflation_last_updated": latest_inflation["recorded_at"] if latest_inflation else None,
    }


@router.get(
    "/history-status",
    summary="Check history status",
    tags=["Investments"],
)
async def get_history_status():
    """Retorna o status do histórico - data do último registro."""
    latest_curves = history_repository.get_latest_curve()
    
    return {
        "has_history": latest_curves is not None,
        "last_updated": latest_curves["recorded_at"] if latest_curves else None,
    }


@router.get(
    "/tickers",
    response_model=TrackedTickersResponse,
    summary="Get all tracked tickers",
    tags=["Investments"],
)
async def get_tracked_tickers():
    """Retorna a lista de todos os tickers registrados."""
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
    "/quote/br/{ticker}",
    response_model=MarketQuoteResponse,
    summary="Get BR stock quote",
    tags=["Investments"],
)
async def get_br_quote(
    ticker: str,
    quantity: float | None = Query(None, description="Optional quantity for portfolio valuation")
):
    """
    Get market quote for a Brazilian stock.
    
    First tries to get from database (latest historical record).
    If not available, fetches from external API and saves to database.
    """
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
            ) from exc
        except Exception as exc:
            logger.exception("Unexpected error fetching BR quote for %s", ticker)
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
    "/quote/us/{ticker}",
    response_model=MarketQuoteResponse,
    summary="Get US stock quote",
    tags=["Investments"],
)
async def get_us_quote(
    ticker: str,
    quantity: float | None = Query(None, description="Optional quantity for portfolio valuation")
):
    """Get market quote for a US stock."""
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
            logger.exception("Unexpected error fetching US quote for %s", ticker)
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
    "/quote/crypto/{slug}",
    response_model=MarketQuoteResponse,
    summary="Get crypto quote",
    tags=["Investments"],
)
async def get_crypto_quote(
    slug: str,
    quantity: float | None = Query(None, description="Optional quantity for portfolio valuation")
):
    """Get market quote for a cryptocurrency."""
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
    "/quote/currency/{from_currency}/{to_currency}",
    response_model=MarketQuoteResponse,
    summary="Get currency quote",
    tags=["Investments"],
)
async def get_currency_quote(
    from_currency: str,
    to_currency: str,
    quantity: float | None = Query(None, description="Optional quantity to convert")
):
    """Get market quote for a currency pair."""
    pair = f"{from_currency.upper()}-{to_currency.upper()}"
    
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
            ) from exc
        except Exception as exc:
            logger.exception("Unexpected error fetching currency quote for %s-%s", from_currency, to_currency)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={"error": "INTERNAL_ERROR", "detail": "Unexpected error fetching quote.", "code": "INTERNAL_ERROR"},
            ) from exc

    response = MarketQuoteResponse(
        ticker=pair,
        unit_price=quote_data["price"],
        updated_at=quote_data["updated_at"],
    )

    if quantity is not None:
        response.quantity = quantity
        response.position_value = round(quote_data["price"] * quantity, 6)

    return response