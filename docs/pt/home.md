# Engine de Precificação de Renda Fixa

Um microsserviço pronto para produção que calcula os preços exatos a mercado dos principais instrumentos de renda fixa brasileiros: títulos públicos do **Tesouro Direto**, **CDB** (Certificado de Depósito Bancário), e **LCI / LCA**.

O sistema busca dados reais do mercado e usa a convenção brasileira de 252 dias úteis para precificar todos os ativos suportados.

## Fontes de Dados

As fórmulas de precificação dependem de dados de mercado reais:

1. **Curvas de Juros (ANBIMA)**: Curvas nominais (Pré) e reais (IPCA+). O sistema interpola linearmente as taxas para qualquer vencimento.
2. **Inflação e Fator Diário (Banco Central do Brasil)**: Variações mensais do IPCA (Série SGS 433) e fator diário da SELIC/CDI (Série SGS 12), usados para calcular o VNA e precificar CDBs CDI-indexados.
3. **Meta SELIC (BCB SGS 11)**: Taxa básica de referência para os títulos Tesouro Selic.

Os dados são buscados por um cron job externo (GitHub Actions) e armazenados no PostgreSQL.

> 📖 **Veja também:** [Configuração do GitHub Actions](github-actions.md) - Como configurar e monitorar o cron job.

## Stack Tecnológico

- **Python 3.12+**
- **FastAPI** — API assíncrona de alta performance com OpenAPI (Swagger).
- **Pydantic** — Tipagem estrita e validação de input.
- **PostgreSQL** — Armazenamento de dados históricos (INSERT only).
- **Pytest** — Suíte completa de testes unitários e de integração.
