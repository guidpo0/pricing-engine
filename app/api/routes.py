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
from app.models.cdb import CDBValueRequest, CDBValueResponse
from app.services import curve_service, inflation_service
from app.services.pricing_engine import calculate_pu
from app.services.cdb_pricing_engine import calculate_cdb
from app.models.lci_lca import LCILCAValueRequest, LCILCAValueResponse
from app.services.lci_lca_pricing_engine import calculate_lci_lca

logger = logging.getLogger(__name__)

router = APIRouter()

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
# Documentation endpoints
# ---------------------------------------------------------------------------

class DocLanguage(str, Enum):
    EN = "en"
    PT = "pt"

@router.get(
    "/docs/readme",
    summary="Get project documentation as HTML",
    tags=["System"],
    response_class=HTMLResponse,
)
async def get_readme(
    lang: DocLanguage = Query(DocLanguage.EN, description="Language of the documentation (en or pt)"),
    page: str = Query("home", description="Page to view: home, bonds, jobs, architecture, integration, api"),
) -> HTMLResponse:
    """Return the raw markdown content of the project documentation rendered as HTML."""
    if page not in ["home", "bonds", "jobs", "architecture", "integration", "cdb", "lci_lca", "api"]:
        page = "home"
        
    base_dir = Path(__file__).resolve().parent.parent.parent
    docs_dir = base_dir / "docs" / lang.value
    
    readme_path = docs_dir / f"{page}.md"
        
    try:
        content = readme_path.read_text(encoding="utf-8")
        
        # Convert markdown to HTML (adding 'toc' extension)
        md = markdown.Markdown(extensions=["toc", "fenced_code", "tables", "nl2br", "sane_lists"])
        content_html = md.convert(content)
        toc_html = getattr(md, "toc", "")
        
        # Language toggle links (preserve current page)
        other_lang = "pt" if lang == DocLanguage.EN else "en"
        other_lang_label = "Ver em Português 🇧🇷" if lang == DocLanguage.EN else "View in English 🇺🇸"
        
        # Navigation Menu
        if lang == DocLanguage.EN:
            menu_title = "Navigation"
            links = {"home": "Home", "bonds": "Tesouro Bonds", "cdb": "CDB", "lci_lca": "LCI & LCA", "integration": "Integration Guide", "architecture": "Architecture (ADR)", "jobs": "Background Jobs", "api": "API Endpoints"}
        else:
            menu_title = "Navegação"
            links = {"home": "Início", "bonds": "Títulos Tesouro", "cdb": "CDB", "lci_lca": "LCI & LCA", "integration": "Guia de Integração", "architecture": "Decisões de Arquitetura", "jobs": "Jobs e Dados", "api": "API e Endpoints"}
            
        nav_items_html = ""
        for p, label in links.items():
            active_style = "font-weight: bold; text-decoration: underline;" if p == page else ""
            nav_items_html += f'<li><a href="?lang={lang.value}&page={p}" style="{active_style}">{label}</a></li>\n'
        
        lang_nav_html = f'''
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
            <a href="?lang={other_lang}&page={page}">{other_lang_label}</a>
            <button id="theme-toggle" style="cursor: pointer; background: none; border: 1px solid var(--border-color); padding: 4px 8px; border-radius: 4px; color: var(--text-color);">🌓</button>
        </div>
        <hr style="border: 0; border-top: 1px solid var(--border-color); margin-bottom: 20px;" />
        <h3>{menu_title}</h3>
        <ul>
            {nav_items_html}
        </ul>
        <hr style="border: 0; border-top: 1px solid var(--border-color); margin-top: 20px; margin-bottom: 20px;" />
        '''
        
        html_template = f"""<!DOCTYPE html>
<html lang="{lang}">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Tesouro Pricing API Docs</title>
    <link id="github-md-css" rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/github-markdown-css/5.5.1/github-markdown.min.css">
    <style>
        :root {{
            --bg-body: #ffffff;
            --bg-sidebar: #f6f8fa;
            --border-color: #d0d7de;
            --text-color: #24292f;
            --link-color: #0969da;
        }}
        [data-theme="dark"] {{
            /* GitHub dark mode colors approximating their palette */
            --bg-body: #0d1117;
            --bg-sidebar: #161b22;
            --border-color: #30363d;
            --text-color: #c9d1d9;
            --link-color: #58a6ff;
        }}
        body {{
            margin: 0;
            padding: 0;
            font-family: -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;
            display: flex;
            height: 100vh;
            background-color: var(--bg-body);
            color: var(--text-color);
        }}
        .sidebar {{
            width: 300px;
            background-color: var(--bg-sidebar);
            border-right: 1px solid var(--border-color);
            overflow-y: auto;
            padding: 20px;
            box-sizing: border-box;
        }}
        .sidebar ul {{
            list-style-type: none;
            padding-left: 15px;
        }}
        .sidebar > div > ul {{
            padding-left: 0;
        }}
        .sidebar a {{
            color: var(--link-color);
            text-decoration: none;
            font-size: 14px;
            display: block;
            padding: 4px 0;
        }}
        .sidebar a:hover {{
            text-decoration: underline;
        }}
        .content-wrapper {{
            flex: 1;
            overflow-y: auto;
            padding: 45px;
            background-color: var(--bg-body);
        }}
        .markdown-body {{
            box-sizing: border-box;
            max-width: 980px;
            margin: 0 auto;
        }}
        @media (max-width: 767px) {{
            body {{
                flex-direction: column;
            }}
            .sidebar {{
                width: 100%;
                height: 30vh;
                border-right: none;
                border-bottom: 1px solid var(--border-color);
            }}
            .content-wrapper {{
                height: 70vh;
                padding: 15px;
            }}
        }}
    </style>
</head>
<body>
    <div class="sidebar">
        {lang_nav_html}
        <h3>TOC (On this page)</h3>
        {toc_html}
    </div>
    <div class="content-wrapper">
        <div class="markdown-body" id="md-body">
            {content_html}
        </div>
    </div>
    <script>
        const htmlEl = document.documentElement;
        const themeToggle = document.getElementById('theme-toggle');
        const themeCss = document.getElementById('github-md-css');
        
        // Load preference
        const savedTheme = localStorage.getItem('theme');
        if (savedTheme === 'dark') {{
            setDark();
        }} else if (savedTheme === 'light') {{
            setLight();
        }} else if (window.matchMedia('(prefers-color-scheme: dark)').matches) {{
            setDark();
        }} else {{
            setLight();
        }}
        
        function setDark() {{
            htmlEl.setAttribute('data-theme', 'dark');
            themeCss.href = 'https://cdnjs.cloudflare.com/ajax/libs/github-markdown-css/5.5.1/github-markdown-dark.min.css';
            localStorage.setItem('theme', 'dark');
        }}
        
        function setLight() {{
            htmlEl.setAttribute('data-theme', 'light');
            themeCss.href = 'https://cdnjs.cloudflare.com/ajax/libs/github-markdown-css/5.5.1/github-markdown-light.min.css';
            localStorage.setItem('theme', 'light');
        }}
        
        themeToggle.addEventListener('click', () => {{
            if (htmlEl.getAttribute('data-theme') === 'dark') {{
                setLight();
            }} else {{
                setDark();
            }}
        }});
    </script>
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
