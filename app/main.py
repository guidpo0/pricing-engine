"""
FastAPI application entrypoint for the Tesouro Direto Pricing Service.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status, Query
from fastapi.responses import JSONResponse, HTMLResponse
import markdown
from pathlib import Path
from enum import Enum

from app.api.routes import router as api_router
from app.api.investments_routes import router as investments_router
from app.config import settings
from app.services import curve_service, inflation_service
from app.services.investment_service import load_cache_to_memory

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
    """Application lifespan handler."""
    logger.info("Starting Tesouro Pricing Service (env=%s)...", settings.app_env)
    load_cache_to_memory()
    yield
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
# Routers & Unprotected Endpoints
# ---------------------------------------------------------------------------
app.include_router(api_router)
app.include_router(investments_router)


class DocLanguage(str, Enum):
    EN = "en"
    PT = "pt"

@app.get(
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
        import logging
        logger = logging.getLogger(__name__)
        logger.error("README file not found at %s", readme_path)
        from fastapi import HTTPException
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "NOT_FOUND", "detail": "Documentation file not found.", "code": "NOT_FOUND"},
        )


@app.get(
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
