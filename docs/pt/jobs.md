# Jobs e Atualização de Dados

A engine **não** realiza requisições lentas em tempo real para serviços externos na hora de precificar um ativo.

Para garantir **latência de milissegundos**, os dados de mercado necessários são mantidos em cache na RAM.

---

## Arquitetura de Dados

### 1. Startup (Lifespan)

Durante a inicialização do Uvicorn, a engine carrega dados em cache do PostgreSQL para a RAM.

> **E se não houver dados em cache?**
> Cada serviço possui constantes de fallback (`_FALLBACK_PRE_CURVE`, `_FALLBACK_LFT_VNA`, etc.) carregadas na RAM. O sistema registra um Warning e sobe normalmente.

### 2. Atualizações de Dados

As atualizações de dados **não** são realizadas por jobs internos em background. Em vez disso, um **cron job externo separado** (GitHub Actions) chama o endpoint `/investments/update-cache` periodicamente.

Esta abordagem:

- Evita rate limiting de APIs externas
- Mantém a API responsiva durante fetches de dados
- Permite escalar independentemente atualizações de dados do servidor da API

### 3. Comportamento em Runtime

Em cada requisição, a API:

1. Primeiro tenta usar o cache em memória (mais rápido)
2. Faz fallback para o histórico do PostgreSQL se o cache em memória estiver obsoloto/ausente
3. Busca da API externa apenas se não houver dados em cache, e salva no PostgreSQL

---

## O Endpoint `/investments/update-cache`

Este endpoint é chamado pelo cron job externo para atualizar todos os dados de mercado:

```bash
curl -X POST https://your-api.com/investments/update-cache \
  -H "X-API-Key: your-token"
```

Ele atualiza:

- **Curvas de Juros** (ANBIMA)
- **Inflação/IPCA+ VNA** (Banco Central)
- **Taxas CDI/SELIC** (Banco Central)
- **Cotações de Ações** (Brasil, EUA)
- **Cotações de Criptomoedas**
- **Taxas de Câmbio**

Todos os dados são salvos no PostgreSQL como registros históricos (INSERT only, nunca UPDATE/DELETE).

---

## Monitoramento

| Endpoint                          | O que informa                                                       |
| --------------------------------- | ------------------------------------------------------------------- |
| `GET /health`                     | `using_fallback: true` indica que pelo menos uma API externa falhou |
| `GET /market/curves`              | Curvas atuais em memória + hora da última atualização               |
| `GET /market/vna`                 | VNA IPCA+ atual + série de inflação em cache                        |
| `GET /investments/history-status` | Timestamp da última atualização de dados do PostgreSQL              |
