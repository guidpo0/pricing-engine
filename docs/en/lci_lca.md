# LCI / LCA — Letra de Crédito Imobiliário / do Agronegócio

The **Pricing Engine** supports mark-to-model valuation for LCI and LCA, computing the current value of an investment based on its index type, with special handling for the grace period (carência) and tax exemption.

LCI and LCA instruments share the same index types as CDBs but are exempt from income tax (IR = 0%).

---

## Supported Index Types

| Code | Description | Rate Example |
|---|---|---|
| `CDI` | Percentage of CDI | `0.95` (= 95% of CDI) |
| `PREFIXADO` | Fixed annual rate | `0.10` (= 10% p.a.) |
| `IPCA` | IPCA + real spread | `0.05` (= IPCA + 5% p.a.) |

---

## Endpoint

### `POST /lci-lca/value`

Calculates the current mark-to-model value of an LCI or LCA.

**Request Body:**
```json
{
  "instrument_type": "LCI",
  "principal": 15000.0,
  "rate": 0.95,
  "index_type": "CDI",
  "purchase_date": "2024-05-01",
  "maturity_date": "2026-05-01",
  "grace_period_days": 90
}
```

**Fields:**
- `instrument_type` — `LCI` or `LCA`.
- `principal` — Original invested amount in BRL.
- `rate` — Rate according to the index type (see table above).
- `index_type` — `CDI`, `PREFIXADO` or `IPCA`.
- `purchase_date` — Purchase date in `YYYY-MM-DD` format (cannot be in the future).
- `maturity_date` — Maturity date.
- `grace_period_days` — Number of days the investor is prohibited from redeeming the instrument.

**Response:**
```json
{
  "instrument_type": "LCI",
  "current_value": 15949.12,
  "yield_amount": 949.12,
  "yield_percentage": 6.3275,
  "redeemable": true,
  "calculation_date": "2026-03-07"
}
```

> The `redeemable` flag indicates if the `grace_period_days` rule allows reselling/redeeming the asset today. Since LCI/LCA are tax-free, the `yield_amount` shown is the net tax-free amount.
