# Como Começar e Endpoints

Provemos um `Makefile` para facilitar o uso local.

### Instalação e Execução

1. **Inicie a API:**
   ```bash
   make run
   ```
2. **Teste a Aplicação:**
   ```bash
   make test
   ```

---

## Endpoints da API

Abaixo estão detalhados os endpoints interativos disponibilizados pela nossa API REST.

### `GET /bonds/price`
Calcula o preço unitário (PU) exato de um título governamental.

**Exemplo:** Precificar um título IPCA+ vencendo em 2035 com 0,2% de spread (taxa) adicional.
```bash
curl "http://localhost:8000/bonds/price?type=IPCA&maturity_date=2035-05-15&spread=0.002"
```

### `POST /portfolio/value`
Recebe uma quantidade fracionária de um título e calcula o valor financeiro total da posição (Mark-to-Market).

**Exemplo:**
```bash
curl -X POST "http://localhost:8000/portfolio/value" \
     -H "Content-Type: application/json" \
     -d '{"bond_type":"IPCA_JUROS","maturity_date":"2040-08-15","quantity":1.5}'
```

### `GET /docs/readme`
Retorna a documentação base em HTML.
- `?lang=en` (padrão) para Inglês
- `?lang=pt` para Português
- `?page=home|bonds|api` para navegar.

### `GET /market/curves` e `GET /market/vna`
Endpoints de sistema (debug) que retornam as curvas de juros e o VNA de inflação carregados na memória neste exato momento e usados para os cálculos.

### `GET /health`
Liveness probe. Verifica se o serviço está de pé e os dados do mercado foram carregados na inicialização.
