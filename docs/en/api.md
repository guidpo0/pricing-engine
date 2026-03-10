# Getting Started & API Endpoints

We provide a `Makefile` for easy local usage.

### Installation & Running

1. **Start the API:**
   ```bash
   make run
   ```
2. **Run tests:**
   ```bash
   make test
   ```

---

## API Endpoints

### Tesouro Direto (Government Bonds)

#### `GET /bonds/price`
Calculates the Preço Unitário (PU) for a government bond.

```bash
curl "http://localhost:8000/bonds/price?type=IPCA&maturity_date=2035-05-15&spread=0.002"
```

#### `POST /portfolio/value`
Accepts a fractional bond quantity and returns the total mark-to-market position value.

```bash
curl -X POST "http://localhost:8000/portfolio/value" \
     -H "Content-Type: application/json" \
     -d '{"bond_type":"IPCA_JUROS","maturity_date":"2040-08-15","quantity":1.5}'
```

---

### CDB

#### `POST /cdb/value`
Calculates the current mark-to-model value of a CDB investment.

```bash
# CDI — 110% CDI since Jun/24
curl -X POST "http://localhost:8000/cdb/value" \
     -H "Content-Type: application/json" \
     -d '{"principal":10000,"rate":1.10,"index_type":"CDI","purchase_date":"2024-06-01","maturity_date":"2027-06-01"}'

# Fixed rate — 12% p.a.
curl -X POST "http://localhost:8000/cdb/value" \
     -H "Content-Type: application/json" \
     -d '{"principal":10000,"rate":0.12,"index_type":"PREFIXADO","purchase_date":"2024-01-01","maturity_date":"2027-01-01"}'

# IPCA + 5%
curl -X POST "http://localhost:8000/cdb/value" \
     -H "Content-Type: application/json" \
     -d '{"principal":10000,"rate":0.05,"index_type":"IPCA","purchase_date":"2024-01-01","maturity_date":"2027-01-01"}'
```

---

### LCI / LCA

#### `POST /lci-lca/value`
Calculates the current mark-to-model value of an LCI or LCA investment.

```bash
# CDI — 95% CDI
curl -X POST "http://localhost:8000/lci-lca/value" \
     -H "Content-Type: application/json" \
     -d '{"instrument_type":"LCI","principal":15000,"rate":0.95,"index_type":"CDI","purchase_date":"2024-05-01","maturity_date":"2026-05-01","grace_period_days":90}'
```

---

### Market Data (Debug)

#### `GET /market/curves`
Returns the Pre and IPCA+ yield curves plus SELIC rate currently loaded in memory.

#### `GET /market/vna`
Returns the current IPCA+ VNA and cached inflation series.

#### `GET /market/quote/{ticker}`
Returns the real-time quote for a Stock or FII via BRAPI, cached to avoid rate limits. Supports the optional `quantity` parameter to calculate the position value.

```bash
curl "http://localhost:8000/api/v1/market/quote/PETR4?quantity=100"
```

#### `GET /health`
Liveness probe — verifies the service is up and market data loaded successfully. Watch for `"using_fallback": true` to detect graceful degradation mode.

---

### Documentation

#### `GET /docs/readme`
Returns this documentation as HTML.
- `?lang=en` — English (default) | `?lang=pt` — Portuguese
- `?page=home|bonds|cdb|lci_lca|integration|architecture|jobs|api`
