"""
API routes for investment cache management.
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
    update_all_cache, get_cache_info
)
from app.utils.database import (
    get_all_tickers, get_all_tickers_us,
    get_all_crypto_slugs, get_all_currency_pairs
)
from app.history import history_repository
from app.history.history_repository import HISTORY_KEYS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/investments", tags=["Investments"], dependencies=[Depends(verify_api_token)])


@router.post(
    "/update-cache",
    summary="Update investment data cache",
    tags=["Investments"],
)
async def update_cache():
    """
    Atualiza o cache persistente de dados de investimentos.
    
    Este endpoint deve ser chamado por um cron job externo (GitHub Actions)
    para atualizar os dados de investimentos periodicamente.
    
    O endpoint:
    - Consulta as APIs externas de investimento
    - Atualiza os dados em memória
    - Salva o resultado no cache persistente (JSON)
    
    O endpoint é idempotente - pode ser chamado várias vezes ao dia.
    """
    try:
        result = await update_all_cache()
        return result
    except Exception as exc:
        logger.exception("Failed to update cache")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "CACHE_UPDATE_ERROR", "detail": str(exc), "code": "CACHE_UPDATE_ERROR"},
        )


@router.get(
    "/cache-info",
    summary="Get cache information",
    tags=["Investments"],
)
async def get_cache_information():
    """Retorna informações sobre o cache persistente."""
    return get_cache_info()


@router.get(
    "/cache-status",
    summary="Check cache status",
    tags=["Investments"],
)
async def get_cache_status():
    """Retorna o status do cache - se está fresco ou precisa de atualização."""
    cache_data = history_repository.get_all()
    updated_at = cache_data.get("updated_at")
    
    is_fresh = history_repository.is_cache_fresh("curves", max_age_hours=24)
    
    return {
        "has_cache": updated_at is not None,
        "updated_at": updated_at,
        "is_fresh": is_fresh
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
    summary="Get BR stock quote with fallback",
    tags=["Investments"],
)
async def get_br_quote(
    ticker: str,
    quantity: float | None = Query(None, description="Optional quantity for portfolio valuation")
):
    """
    Get market quote for a Brazilian stock with fallback.
    
    Se o cache não existir, executa automaticamente a atualização.
    """
    cached_data = history_repository.get(HISTORY_KEYS["br_stocks"])
    
    if not cached_data:
        logger.info("No cache found, triggering automatic update...")
        await update_all_cache()
    
    try:
        quote_data = await market_service.get_market_quote(ticker)
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
    summary="Get US stock quote with fallback",
    tags=["Investments"],
)
async def get_us_quote(
    ticker: str,
    quantity: float | None = Query(None, description="Optional quantity for portfolio valuation")
):
    """Get market quote for a US stock with fallback."""
    cached_data = history_repository.get(HISTORY_KEYS["us_stocks"])
    
    if not cached_data:
        logger.info("No cache found, triggering automatic update...")
        await update_all_cache()
    
    try:
        quote_data = await us_market_service.get_us_market_quote(ticker)
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
    summary="Get crypto quote with fallback",
    tags=["Investments"],
)
async def get_crypto_quote(
    slug: str,
    quantity: float | None = Query(None, description="Optional quantity for portfolio valuation")
):
    """Get market quote for a cryptocurrency with fallback."""
    cached_data = history_repository.get(HISTORY_KEYS["crypto"])
    
    if not cached_data:
        logger.info("No cache found, triggering automatic update...")
        await update_all_cache()
    
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
    "/quote/currency/{from_currency}/{to_currency}",
    response_model=MarketQuoteResponse,
    summary="Get currency quote with fallback",
    tags=["Investments"],
)
async def get_currency_quote(
    from_currency: str,
    to_currency: str,
    quantity: float | None = Query(None, description="Optional quantity to convert")
):
    """Get market quote for a currency pair with fallback."""
    cached_data = history_repository.get(HISTORY_KEYS["currencies"])
    
    if not cached_data:
        logger.info("No cache found, triggering automatic update...")
        await update_all_cache()
    
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