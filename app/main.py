"""
FastAPI application entrypoint for the Tesouro Direto Pricing Service.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.config import settings
from app.jobs.update_market_data import run_initial_data_load, start_scheduler, stop_scheduler

# ---------------------------------------------------------------------------
# Logging configuration
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=settings.log_level.upper(),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Application lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start the scheduler and eagerly fetch market data on startup."""
    logger.info("Starting Tesouro Pricing Service (env=%s)...", settings.app_env)
    start_scheduler()
    await run_initial_data_load()
    yield
    stop_scheduler()
    logger.info("Tesouro Pricing Service stopped.")


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Tesouro Direto Pricing Engine",
    description=(
        "A production-ready microservice that calculates mark-to-market prices "
        "(Preço Unitário - PU) for Brazilian government bonds from the "
        "**Tesouro Direto** program.\n\n"
        "Supported bonds:\n"
        "- **PREFIXADO** — Tesouro Prefixado (LTN)\n"
        "- **PREFIXADO_JUROS** — Tesouro Prefixado com juros semestrais (NTN-F)\n"
        "- **IPCA** — Tesouro IPCA+ (NTN-B Principal)\n"
        "- **IPCA_JUROS** — Tesouro IPCA+ com juros semestrais (NTN-B)\n"
        "- **SELIC** — Tesouro Selic (LFT)\n\n"
        "Market data is automatically refreshed daily from ANBIMA and Banco Central do Brasil."
    ),
    version="1.0.0",
    contact={
        "name": "Pricing Engine",
        "url": "https://github.com/guidpo0/pricing-engine",
    },
    license_info={
        "name": "MIT",
    },
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(router)

# ---------------------------------------------------------------------------
# Global exception handlers
# ---------------------------------------------------------------------------

@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"error": "VALIDATION_ERROR", "detail": str(exc), "code": "VALIDATION_ERROR"},
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception on %s %s", request.method, request.url)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error": "INTERNAL_ERROR", "detail": "An unexpected error occurred.", "code": "INTERNAL_ERROR"},
    )
