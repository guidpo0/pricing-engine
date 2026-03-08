# CDB — Certificado de Depósito Bancário

The **Pricing Engine** supports mark-to-model valuation of CDBs, computing the current value of an investment based on its index type and live market rates fetched daily from the Brazilian Central Bank.

---

## Supported Index Types

| Code | Description | Rate Example |
|---|---|---|
| `CDI` | Percentage of CDI | `1.10` (= 110% of CDI) |
| `PREFIXADO` | Fixed annual rate | `0.12` (= 12% p.a.) |
| `IPCA` | IPCA + real spread | `0.05` (= IPCA + 5% p.a.) |

---

## Endpoint

### `POST /cdb/value`

Calculates the current mark-to-model value of a CDB investment.

**Request Body:**
```json
{
  "principal": 10000.0,
  "rate": 1.10,
  "index_type": "CDI",
  "purchase_date": "2024-06-01",
  "maturity_date": "2027-06-01"
}
```

**Fields:**
- `principal` — Original invested amount in BRL.
- `rate` — Rate according to the index type (see table above).
- `index_type` — `CDI`, `PREFIXADO` or `IPCA`.
- `purchase_date` — Purchase date in `YYYY-MM-DD` format (cannot be in the future).
- `maturity_date` — CDB maturity date.

**Response:**
```json
{
  "index_type": "CDI",
  "principal": 10000.0,
  "rate": 1.1,
  "purchase_date": "2024-06-01",
  "maturity_date": "2027-06-01",
  "current_value": 12881.07,
  "yield_amount": 2881.07,
  "yield_percentage": 28.8107,
  "is_matured": false,
  "calculation_date": "2026-03-07"
}
```

---

## Pricing Formulas

### CDI
The engine fetches CDI/SELIC daily factors from the Brazilian Central Bank (BCB SGS Series 12) and compounds returns day by day:
```
value = principal × Π(1 + daily_CDI_factor × contracted_percentage)
```
> Per each business day from purchase_date to today.

### Prefixado (Fixed Rate)
Standard compound interest at the contracted annual rate:
```
value = principal × (1 + rate) ^ years_elapsed
```

### IPCA (Inflation Linked)
Accumulated inflation since purchase multiplied by the contracted real yield:
```
value = principal × inflation_factor × (1 + real_rate) ^ years_elapsed
```
> `inflation_factor` is computed by compounding monthly IPCA readings (BCB SGS Series 433) since the purchase date.

---

## Post-Maturity Behaviour

If the CDB has already matured, the engine computes the value **as of the maturity date** (the instrument stopped accruing after that point). The response includes `"is_matured": true` so that your application can handle this case appropriately.

---

## Market Data Sources

| Data | Source | BCB Series |
|---|---|---|
| CDI daily factor | Brazilian Central Bank | SGS 12 |
| IPCA monthly readings | Brazilian Central Bank | SGS 433 |
