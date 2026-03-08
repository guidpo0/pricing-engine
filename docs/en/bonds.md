# Supported Bonds

The service covers the 5 main retail treasury bonds available for trading:

| Bond Type | API identifier | Methodology |
|-----------|----------------|-------------|
| Tesouro Prefixado | `PREFIXADO` | Discount nominal value by the nominal (Pre) yield curve. |
| Tesouro Prefixado com juros | `PREFIXADO_JUROS`| NPV of semi-annual 10% coupons + face value at nominal curve. |
| Tesouro IPCA+ | `IPCA` | Discount VNA by the real (IPCA+) yield curve. |
| Tesouro IPCA+ com juros | `IPCA_JUROS` | NPV of semi-annual 6% coupons on VNA + VNA at real curve. |
| Tesouro Selic | `SELIC` | VNA SELIC updated daily since 2000, discounted by market spread. |
