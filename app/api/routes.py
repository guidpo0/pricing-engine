"""
API routes for the Tesouro Direto pricing service.
"""
from __future__ import annotations

import logging
from datetime import date
from enum import Enum
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import HTMLResponse
import markdown

from app.models.bond import (
    BondPriceRequest,
    BondPriceResponse,
    BondType,
    PortfolioValueRequest,
    PortfolioValueResponse,
)
from app.services import curve_service, inflation_service
from app.services.pricing_engine import calculate_pu

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Bond pricing endpoint
# ---------------------------------------------------------------------------

@router.get(
    "/bonds/price",
    response_model=BondPriceResponse,
    summary="Get mark-to-market price for a bond",
    tags=["Pricing"],
)
async def get_bond_price(
    type: BondType = Query(..., description="Bond type (PREFIXADO, PREFIXADO_JUROS, IPCA, IPCA_JUROS, SELIC)"),
    maturity_date: date = Query(..., description="Bond maturity date (YYYY-MM-DD)"),
    spread: float = Query(default=0.0, ge=-0.05, le=0.05, description="Optional spread over benchmark (decimal)"),
) -> BondPriceResponse:
    """
    Calculate the Preço Unitário (PU) of a Tesouro Direto bond.

    Uses the current in-memory yield curve and VNA to produce a mark-to-market price.
    """
    if maturity_date <= date.today():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": "INVALID_MATURITY",
                "detail": "maturity_date must be in the future.",
                "code": "INVALID_MATURITY",
            },
        )

    try:
        result = calculate_pu(type, maturity_date, spread=spread)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "PRICING_ERROR", "detail": str(exc), "code": "PRICING_ERROR"},
        ) from exc
    except Exception as exc:
        logger.exception("Unexpected error pricing bond type=%s maturity=%s", type, maturity_date)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "INTERNAL_ERROR", "detail": "Unexpected pricing error.", "code": "INTERNAL_ERROR"},
        ) from exc

    return BondPriceResponse(
        bond_type=type,
        maturity_date=maturity_date,
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


# ---------------------------------------------------------------------------
# Documentation endpoints
# ---------------------------------------------------------------------------

class DocLanguage(str, Enum):
    EN = "en"
    PT = "pt"

@router.get(
    "/docs/readme",
    summary="Get project documentation (README) as HTML",
    tags=["System"],
    response_class=HTMLResponse,
)
async def get_readme(
    lang: DocLanguage = Query(DocLanguage.EN, description="Language of the documentation (en or pt)"),
) -> HTMLResponse:
    """Return the raw markdown content of the project README rendered as HTML."""
    base_dir = Path(__file__).resolve().parent.parent.parent
    
    if lang == DocLanguage.PT:
        readme_path = base_dir / "README_pt.md"
    else:
        readme_path = base_dir / "README.md"
        
    try:
        content = readme_path.read_text(encoding="utf-8")
        
        # Convert markdown to HTML
        content_html = markdown.markdown(
            content,
            extensions=["fenced_code", "tables", "nl2br", "sane_lists"]
        )
        
        html_template = f"""<!DOCTYPE html>
<html lang="{lang}">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Tesouro Pricing API Docs</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/github-markdown-css/5.5.1/github-markdown.min.css">
    <style>
        .markdown-body {{
            box-sizing: border-box;
            min-width: 200px;
            max-width: 980px;
            margin: 0 auto;
            padding: 45px;
        }}
        @media (max-width: 767px) {{
            .markdown-body {{
                padding: 15px;
            }}
        }}
    </style>
</head>
<body class="markdown-body">
{content_html}
</body>
</html>"""
        return HTMLResponse(content=html_template, status_code=200)
    except FileNotFoundError:
        logger.error("README file not found at %s", readme_path)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "NOT_FOUND", "detail": "Documentation file not found.", "code": "NOT_FOUND"},
        )

# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@router.get(
    "/health",
    summary="Health check",
    tags=["System"],
    status_code=status.HTTP_200_OK,
)
async def health_check() -> dict:
    """Liveness probe — returns OK when the service is running."""
    curve_info = curve_service.get_cache_info()
    inflation_info = inflation_service.get_cache_info()
    return {
        "status": "ok",
        "curves_last_updated": curve_info["last_updated"],
        "vna_last_updated": inflation_info["last_updated"],
        "curves_using_fallback": curve_info["using_fallback"],
        "vna_using_fallback": inflation_info["using_fallback"],
    }
