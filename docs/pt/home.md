# Engine de Precificação do Tesouro Direto

Um microsserviço pronto para produção que calcula os preços exatos a mercado (Preço Unitário - PU) dos títulos públicos brasileiros do programa **Tesouro Direto**.

O sistema busca dados reais do mercado diariamente e usa a convenção brasileira de 252 dias úteis para precificar todos os títulos de varejo disponíveis.

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
