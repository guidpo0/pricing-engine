# Fixed Income Pricing Engine

A production-ready microservice that calculates exact mark-to-market prices for the main Brazilian fixed income instruments: **Tesouro Direto** government bonds, **CDB** (Certificado de Depósito Bancário), and **LCI / LCA** (Letra de Crédito Imobiliário / do Agronegócio).

The system fetches real market data daily and uses the Brazilian 252 business-day convention for all pricing calculations.

## Data Sources

Pricing formulas depend on real market data fetched automatically:

1. **Yield Curves (ANBIMA)**: Nominal (Pre) and real (IPCA+) curves fetched daily. The engine linearly interpolates rates for any maturity.
2. **Inflation & Daily Factor (Brazilian Central Bank)**: Monthly IPCA readings (SGS Series 433) and the daily SELIC/CDI factor (SGS Series 12), used to compute VNA and price CDI-indexed CDBs.
3. **SELIC Target Rate (BCB SGS 11)**: The policy rate reference for Tesouro Selic bonds.

Background jobs (APScheduler) refresh this data asynchronously every day.

## Technology Stack

- **Python 3.12+**
- **FastAPI** — High-performance async API with OpenAPI (Swagger).
- **Pydantic** — Strict typing and input validation.
- **APScheduler** — Cron scheduling for curves and index updates.
- **Pytest** — Full unit and integration test suite.
