# LCI / LCA — Letra de Crédito Imobiliário / do Agronegócio

O **Pricing Engine** suporta precificação por marcação a modelo (*Mark-to-Model*) para LCI e LCA, calculando o valor atual de um investimento baseado no seu indexador, com tratamento especial para a carência e isenção de impostos.

LCIs e LCAs compartilham os mesmos indexadores que os CDBs, mas são isentos de Imposto de Renda (IR = 0%).

---

## Tipos de Indexadores Suportados

| Código | Descrição | Exemplo de taxa |
|---|---|---|
| `CDI` | Percentual do CDI | `0.95` (= 95% do CDI) |
| `PREFIXADO` | Taxa fixa anual | `0.10` (= 10% a.a.) |
| `IPCA` | IPCA + Spread real | `0.05` (= IPCA + 5% a.a.) |

---

## Endpoint

### `POST /lci-lca/value`

Calcula o valor atual de uma LCI ou LCA.

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

**Campos:**
- `instrument_type` — `LCI` ou `LCA`.
- `principal` — Valor investido originalmente em reais.
- `rate` — Taxa conforme o indexador (ver tabela acima).
- `index_type` — `CDI`, `PREFIXADO` ou `IPCA`.
- `purchase_date` — Data da compra no formato `AAAA-MM-DD` (não pode ser futura).
- `maturity_date` — Data de vencimento do ativo.
- `grace_period_days` — Dias de carência onde não é permitido o resgate.

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

> A flag `redeemable` (resgatável) indica se a carência do ativo já passou hoje. Por serem leads isentos de IR, o retorno demonstrado no `yield_amount` reflete o ganho líquido para o investidor.
