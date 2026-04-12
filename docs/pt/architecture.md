# Decisões de Arquitetura (ADR)

Este documento registra as principais decisões arquiteturais tomadas durante o design do **Pricing Engine do Tesouro Direto**, bem como as motivações técnicas por trás de cada escolha.

---

## 1. Armazenamento Híbrido: PostgreSQL + Cache em Memória

O sistema usa **PostgreSQL como armazenamento histórico persistente** e **memória RAM** para cálculos ativos de precificação.

### Por que PostgreSQL?

- **Histórico Persistente:** Diferentemente de dados efêmeros em memória, o PostgreSQL sobrevive a reinicializações de container (importante no tier gratuito do Render onde containers dormem após 15 minutos).
- **Jobs Cron Externos:** Atualizações de dados acontecem via cron job externo separado (GitHub Actions), evitando problemas de rate limiting.
- **Análise Histórica:** Ter dados históricos habilita future features como gráficos de preços e análise de tendências.

### Por que Cache em Memória?

- **Latência Sub-milisegundos:** Endpoints de precificação precisam de acesso ultra-rápido a curvas de juros e dados VNA.
- **Padrão de Leitura:** A maioria das requisições são leituras (cálculos de precificação), com escritas raras (cron job externo).

### Fluxo de Dados

1. Cron job externo chama `/investments/update-cache` → dados salvos no PostgreSQL
2. Na inicialização da API, dados carregados do PostgreSQL para RAM
3. Em cada requisição de precificação, cache em memória é usado primeiro
4. Se cache está obsoloto/ausente, PostgreSQL é consultado
5. Se PostgreSQL está vazio, API externa é chamada (e resultado salvo no PostgreSQL)

---

## 2. Padrão de Resiliência: Degradação Suave (Fallba)

O código possui constantes de _fallback_ mockadas (`_FALLBACK_PRE_CURVE`, `_FALLBACK_IPCA_CURVE`) que são carregadas na RAM caso as chamadas de API externas falhem.

### Por que?

- Se você for realizar o deploy da aplicação exatamente em um momento de instabilidade nos servidores governamentais (SGS BCB ou ANBIMA), a aplicação poderia simplesmente "crashar" e não subir.
- Nós priorizamos a **Disponibilidade** em detrimento de uma exatidão momentânea.
- **Degradação Suave:** A API loga um erro avisando da indisponibilidade, sobe usando os dados de fallback, e permite que as carteiras continuem sendo precificadas.
- Essa condição pode ser monitorada acessando a rota `/health` e observando `"using_fallback": true`.

---

## 3. Jobs Cron Externos vs Workers Internos

As atualizações de dados são realizadas por um **cron job externo separado** (GitHub Actions), não por workers internos em background.

### Por que?

- **Evitar Rate Limiting:** Workers internos chamando APIs externas em cada requisição causavam problemas de rate limit com a AwesomeAPI.
- **Separação de Responsabilidades:** Servidores de API permanecem responsivos; busca de dados é desacoplada.
- **Simplicidade:** Não há necessidade de APScheduler ou complexidade similar para tarefas periódicas simples.
- **Escalabilidade:** Cron externo pode ser escalado independentemente dos servidores de API.

### Implementação

- Workflow do GitHub Actions roda em.schedule (ex: a cada 4 horas)
- Chama endpoint `POST /investments/update-cache` com API key
- Todos os dados são salvos como registros INSERT-only no PostgreSQL (nunca UPDATE/DELETE)
