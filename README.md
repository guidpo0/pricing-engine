# Tesouro Direto Pricing Engine

A production-ready microservice that calculates exact mark-to-market prices (Preço Unitário - PU) for Brazilian government bonds from the **Tesouro Direto** program. 

The engine fetches live market data daily and uses the Brazilian 252 business-day convention to price all available retail government bonds.

## Supported Bonds

The service covers the 5 main retail treasury bonds:

| Bond Type | API identifier | Methodology |
|-----------|----------------|-------------|
| Tesouro Prefixado | `PREFIXADO` | Discount nominal value by the nominal (Pre) yield curve. |
| Tesouro Prefixado com juros | `PREFIXADO_JUROS`| NPV of semi-annual 10% coupons + face value at nominal curve. |
| Tesouro IPCA+ | `IPCA` | Discount VNA by the real (IPCA+) yield curve. |
| Tesouro IPCA+ com juros | `IPCA_JUROS` | NPV of semi-annual 6% coupons on VNA + VNA at real curve. |
| Tesouro Selic | `SELIC` | VNA SELIC updated daily since 2000, discounted by market spread. |

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

---

## 🚀 Getting Started

We provide a convenient `Makefile` to simplify local development.

### Requirements
- Python 3.12+
- `make`

### Installation & Running

1. **Start the API:**
   ```bash
   make run
   ```
   *This single command will create a virtual environment (`.venv`), install all requirements, and start the Uvicorn server on port 8000.*

2. **Test the Application:**
   ```bash
   make test
   ```
   *Runs the 34+ unit and integration tests using `pytest`.*

3. **Explore the Docs:**
   Open your browser and navigate to:
   - [http://localhost:8000/docs](http://localhost:8000/docs) (Swagger UI)

### Bruno API Collection
You can easily interact with the endpoints by opening the [`docs/collection`](docs/collection) folder in **Bruno** (an open-source API client). It contains pre-configured requests for all available routes.

---

## API Endpoints

### `GET /bonds/price`
Calculates the exact unit price (PU) of a specific bond.

**Example:** Price an IPCA+ bond maturing in 2035 with a 0.2% additional spread.
```bash
curl "http://localhost:8000/bonds/price?type=IPCA&maturity_date=2035-05-15&spread=0.002"
```

### `POST /portfolio/value`
Takes a fractional quantity of a bond and calculates the total mark-to-market position value.

**Example:**
```bash
curl -X POST "http://localhost:8000/portfolio/value" \
     -H "Content-Type: application/json" \
     -d '{"bond_type":"IPCA_JUROS","maturity_date":"2040-08-15","quantity":1.5}'
```

### `GET /market/curves` and `GET /market/vna`
Debug endpoints that expose the in-memory yield curves and inflation data currently being used for calculations.

### `GET /health`
Liveness probe. Verify if the scheduler is active and data successfully loaded.
