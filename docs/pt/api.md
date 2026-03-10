# Como Começar e Endpoints

Disponibilizamos um `Makefile` para facilitar o uso local.

### Instalação e Execução

1. **Inicie a API:**
   ```bash
   make run
   ```
2. **Execute os testes:**
   ```bash
   make test
   ```

---

## Endpoints da API

### Tesouro Direto

#### `GET /bonds/price`
Calcula o Preço Unitário (PU) de um título público.

```bash
curl "http://localhost:8000/bonds/price?type=IPCA&maturity_date=2035-05-15&spread=0.002"
```

#### `POST /portfolio/value`
Recebe quantidade fracionária de um título e calcula o valor financeiro total da posição.

```bash
curl -X POST "http://localhost:8000/portfolio/value" \
     -H "Content-Type: application/json" \
     -d '{"bond_type":"IPCA_JUROS","maturity_date":"2040-08-15","quantity":1.5}'
```

---

### CDB

#### `POST /cdb/value`
Calcula o valor atual (Mark-to-Model) de um investimento em CDB.

```bash
# CDI — 110% do CDI desde Jun/24
curl -X POST "http://localhost:8000/cdb/value" \
     -H "Content-Type: application/json" \
     -d '{"principal":10000,"rate":1.10,"index_type":"CDI","purchase_date":"2024-06-01","maturity_date":"2027-06-01"}'

# Prefixado — 12% a.a.
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
Calcula o valor atual (Mark-to-Model) de um investimento em LCI ou LCA.

```bash
# CDI — 95% CDI
curl -X POST "http://localhost:8000/lci-lca/value" \
     -H "Content-Type: application/json" \
     -d '{"instrument_type":"LCI","principal":15000,"rate":0.95,"index_type":"CDI","purchase_date":"2024-05-01","maturity_date":"2026-05-01","grace_period_days":90}'
```

---

### Dados de Mercado (Debug)

#### `GET /market/curves`
Retorna as curvas de juros (Pré e IPCA+) e a taxa SELIC carregadas na memória.

#### `GET /market/vna`
Retorna o VNA atual do IPCA+ e a série de inflação em cache.

#### `GET /market/tickers`
Retorna a lista de todos os ativos (`br_tickers`, `us_tickers`, `crypto_slugs` e `currencies`) sendo ativamente rastreados e atualizados em background no banco de dados SQLite.

#### `GET /market/quote/{ticker}`
Retorna a cotação em tempo real de uma Ação ou FII via BRAPI, com cache para evitar rate limits. Suporta o parâmetro opcional `quantity` para calcular o valor da posição.

```bash
curl "http://localhost:8000/market/quote/PETR4?quantity=100"
```

#### `GET /market/quote/us/{ticker}`
Retorna a cotação em tempo real de uma Ação Americana ou ETF via TwelveData. Rate limit tratado com cache fallback.

```bash
curl "http://localhost:8000/market/quote/us/AAPL"
```

#### `GET /market/quote/crypto/{slug}`
Retorna a cotação de uma criptomoeda via CoinMarketCap usando o seu identificador (slug).

```bash
curl "http://localhost:8000/market/quote/crypto/bitcoin?quantity=0.5"
```

#### `GET /market/currency/{from_currency}/{to_currency}`
Retorna a taxa de conversão atual entre duas moedas via AwesomeAPI.

```bash
curl "http://localhost:8000/market/currency/USD/BRL"
```

#### `GET /health`
Liveness probe — verifica se o serviço está ativo e se os dados de mercado foram carregados com sucesso. Observe `"using_fallback": true` para detectar modo de degradação.

---

### Documentação

#### `GET /docs/readme`
Retorna a documentação em HTML.
- `?lang=pt` — Português | `?lang=en` — Inglês (padrão)
- `?page=home|bonds|cdb|lci_lca|integration|architecture|jobs|api`
