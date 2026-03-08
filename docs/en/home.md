# Tesouro Direto Pricing Engine

A production-ready microservice that calculates exact mark-to-market prices (Preço Unitário - PU) for Brazilian government bonds from the **Tesouro Direto** program. 

The engine fetches live market data daily and uses the Brazilian 252 business-day convention to price all available retail government bonds.

## Data Sources

The pricing formulas rely on two real-time Brazilian financial markets:
1. **Yield Curves (ANBIMA)**: Daily nominal (Pre) and real (IPCA+) yield curves fetched automatically. Contains linear interpolation for arbitrary bond tenors.
2. **Inflation Index (Banco Central do Brasil)**: Daily fetched IPCA monthly variations (SGS series 433) and SELIC target rates (SGS series 11) to rigorously calculate the current base VNA (Valor Nominal Atualizado).

Background jobs handle pulling this data asynchronously onto the FastAPI service loops every day.

## Tech Stack

- **Python 3.12+**
- **FastAPI** — High performance async API and OpenAPI docs.
- **Pydantic** — Strict type enforcement and input validation.
- **APScheduler** — Asynchronous cron scheduling for fetching external curves.
- **Pytest** — Complete test suite for pricing permutations.
