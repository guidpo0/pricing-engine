# Engine de Precificação do Tesouro Direto

Um microsserviço pronto para produção que calcula os preços exatos a mercado (Preço Unitário - PU) dos títulos públicos brasileiros do programa **Tesouro Direto**.

O sistema busca dados reais do mercado diariamente e usa a convenção brasileira de 252 dias úteis para precificar todos os títulos de varejo disponíveis.

## Títulos Suportados

O serviço cobre os 5 principais títulos do Tesouro:

| Tipo do Título | Identificador da API | Metodologia |
|-----------|----------------|-------------|
| Tesouro Prefixado | `PREFIXADO` | Desconto do valor nominal pela curva de juros nominal (Pré). |
| Tesouro Prefixado com juros | `PREFIXADO_JUROS`| VPL de cupons semestrais de 10% + valor de face na curva pré. |
| Tesouro IPCA+ | `IPCA` | Desconto do VNA pela curva de juros real (IPCA+). |
| Tesouro IPCA+ com juros | `IPCA_JUROS` | VPL de cupons semestrais de 6% sobre o VNA + retorno do VNA na curva real. |
| Tesouro Selic | `SELIC` | VNA SELIC atualizado diariamente desde 2000, descontado pelo spread de mercado. |

## Fontes de Dados

As fórmulas de precificação dependem de dois mercados financeiros reais:
1. **Curvas de Juros (ANBIMA)**: Curvas nominais (Pré) e reais (IPCA+) buscadas diariamente. O sistema interpola linearmente as taxas para qualquer vencimento.
2. **Índice de Inflação (Banco Central do Brasil)**: Variações mensais do IPCA (Série SGS 433) e meta SELIC (Série SGS 11) buscadas diariamente para calcular o VNA base atualizado.

Jobs em background (APScheduler) atualizam estes dados de forma assíncrona todos os dias.

## Stack Tecnológico

- **Python 3.12+**
- **FastAPI** — API assíncrona de alta performance com OpenAPI (Swagger).
- **Pydantic** — Tipagem estrita e validação de input.
- **APScheduler** — Agendamento cron para buscar as curvas e índices.
- **Pytest** — Suíte completa de testes unitários e de integração.

---

## 🚀 Como Começar

Provemos um `Makefile` para facilitar o uso local.

### Requisitos
- Python 3.12+
- `make`

### Instalação e Execução

1. **Inicie a API:**
   ```bash
   make run
   ```
   *Este comando vai criar automaticamente o ambiente virtual (`.venv`), instalar os requisitos e iniciar o Uvicorn na porta 8000.*

2. **Teste a Aplicação:**
   ```bash
   make test
   ```
   *Roda os 34+ testes unitários usando o `pytest`.*

3. **Explore as rotas visualmente:**
   Abra seu navegador em:
   - [http://localhost:8000/docs](http://localhost:8000/docs) (Swagger UI)

### Bruno API Collection
Você pode interagir facilmente com os endpoints abrindo a pasta [`docs/collection`](docs/collection) no **Bruno** (um cliente de API open-source). Ele já contém as requisições configuradas.

---

## Endpoints da API

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
Retorna este conteúdo de documentação no formato JSON.
- `lang=en` (padrão) para Inglês
- `lang=pt` para Português

**Exemplo:**
```bash
curl "http://localhost:8000/docs/readme?lang=pt"
```

### `GET /market/curves` e `GET /market/vna`
Endpoints de sistema (debug) que retornam as curvas de juros e o VNA carregados na memória neste exato momento e usados para os cálculos.

### `GET /health`
Liveness probe. Verifica se o serviço está de pé e os dados do mercado foram carregados.
