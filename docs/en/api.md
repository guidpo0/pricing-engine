# Getting Started & API Endpoints

We provide a convenient `Makefile` to simplify local development.

### Installation & Running

1. **Start the API:**
   ```bash
   make run
   ```
2. **Test the Application:**
   ```bash
   make test
   ```

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

### `GET /docs/readme`
Returns this HTML documentation. Use the `page` query param to navigate, or `lang` to set language.
- `?lang=en` (default) for English
- `?lang=pt` for Portuguese

### `GET /market/curves` and `GET /market/vna`
Debug endpoints that expose the in-memory yield curves and inflation data currently being used for calculations.

### `GET /health`
Liveness probe. Verify if the scheduler is active and data successfully loaded.
