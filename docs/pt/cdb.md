# CDB — Certificado de Depósito Bancário

O **Pricing Engine** suporta a precificação por marcação a modelo (*Mark-to-Model*) de CDBs, calculando o valor atual de um investimento baseado no seu indexador e nas taxas de mercado captadas diariamente.

---

## Tipos de Indexadores Suportados

| Código | Nome | Exemplo de taxa |
|---|---|---|
| `CDI` | Percentual do CDI | `1.10` (= 110% do CDI) |
| `PREFIXADO` | Taxa Fixa anual | `0.12` (= 12% a.a.) |
| `IPCA` | IPCA + Spread real | `0.05` (= IPCA + 5% a.a.) |

---

## Endpoint

### `POST /cdb/value`

Calcula o valor atual de mercado de um CDB.

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

**Campos:**
- `principal` — Valor investido originalmente em reais.
- `rate` — Taxa conforme o indexador (ver tabela acima).
- `index_type` — `CDI`, `PREFIXADO` ou `IPCA`.
- `purchase_date` — Data da compra no formato `AAAA-MM-DD` (não pode ser futura).
- `maturity_date` — Data de vencimento do CDB.

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

## Fórmulas de Cálculo

### CDI
O motor busca diariamente os fatores da SELIC/CDI do Banco Central (BCB SGS Série 12) e compõe o rendimento dia a dia:
```
valor = principal × Π(1 + fator_diário_CDI × percentual_contratado)
```
> Para cada dia útil entre a data de compra e hoje.

### Prefixado
Juros compostos simples pela taxa anual contratada:
```
valor = principal × (1 + taxa)^anos_decorridos
```

### IPCA
Inflação acumulada desde a compra multiplicada pelo juro real contratado:
```
valor = principal × fator_inflação × (1 + taxa_real)^anos_decorridos
```
> O `fator_inflação` é obtido acumulando os meses do IPCA (BCB SGS Série 433) desde a data de compra.

---

## Comportamento após o Vencimento

Se o CDB já venceu (`is_matured: true`), o motor calcula o valor **na data de vencimento** (o CDB parou de render após essa data). A resposta inclui `is_matured: true` para que o sistema cliente possa tratar esse caso.

---

## Fontes de Dados

| Dado | Fonte | Série BCB |
|---|---|---|
| Fator diário CDI | Banco Central do Brasil | SGS 12 |
| Inflação IPCA | Banco Central do Brasil | SGS 433 |
