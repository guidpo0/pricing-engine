# Fixed Income Pricing Engine

A production-ready microservice that calculates exact mark-to-market prices for the main Brazilian fixed income instruments: **Tesouro Direto** government bonds, **CDB** (Certificado de Depósito Bancário), and **LCI / LCA** (Letra de Crédito Imobiliário / do Agronegócio).

The system fetches real market data and uses the Brazilian 252 business-day convention for all pricing calculations.

## Data Sources

Pricing formulas depend on real market data:

1. **Yield Curves (ANBIMA)**: Nominal (Pre) and real (IPCA+) curves. The engine linearly interpolates rates for any maturity.
2. **Inflation & Daily Factor (Brazilian Central Bank)**: Monthly IPCA readings (SGS Series 433) and the daily SELIC/CDI factor (SGS Series 12), used to compute VNA and price CDI-indexed CDBs.
3. **SELIC Target Rate (BCB SGS 11)**: The policy rate reference for Tesouro Selic bonds.

Data is fetched by an external cron job (GitHub Actions) and stored in PostgreSQL.

> 📖 **See also:** [GitHub Actions Setup](github-actions.md) - How to configure and monitor the cron job.

## Technology Stack

- **Python 3.12+**
- **FastAPI** — High-performance async API with OpenAPI (Swagger).
- **Pydantic** — Strict typing and input validation.
- **PostgreSQL** — Historical data storage (INSERT only).
- **Pytest** — Full unit and integration test suite.
