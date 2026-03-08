# Jobs e Atualização de Dados

Um dos pontos mais críticos do sistema é não depender de requisições lentas em tempo real ("*on-the-fly*") para serviços externos na hora de precificar um ativo.

Para garantir **latência de milissegundos** em todos os endpoints, os dados de mercado necessários são mantidos na RAM através de um cache local, que é constantemente atualizado em segundo plano.

---

## Ciclo de Vida do Scheduler

A aplicação utiliza a biblioteca `APScheduler` com o executor `AsyncIOScheduler`. Ele foi escolhido por ser nativo do `asyncio` e não bloquear o Event Loop do FastAPI.

1. **Startup (Lifespan):** Durante a inicialização do Uvicorn, o FastAPI dispara os eventos de `startup`. Neste momento, a engine realiza uma primeira busca nas APIs externas (**ANBIMA**, **Banco Central**) de forma concorrente via `asyncio.gather`.

   > **E se a API externa falhar no momento do boot?**
   > Para garantir que a engine *nunca* deixe de subir por instabilidades em servidores do governo/ANBIMA, existem dados de fallback (`_FALLBACK_PRE_CURVE`, `_FALLBACK_LFT_VNA`, etc.) definidos nos arquivos de serviço. O sistema registra um *Warning*, carrega esses valores na RAM e sobe normalmente.

2. **Escalonamento:** Após popular a RAM, o `APScheduler` entra em ação, rodando em background. **Nas horas programadas, ele tenta novamente as APIs externas.** Quando o serviço do governo normalizar, substitui silenciosa e automaticamente o cache.

3. **Shutdown (Lifespan):** O encerramento limpo da aplicação sinaliza o Scheduler para parar graciosamente.

---

## Os Jobs

O arquivo `app/jobs/update_market_data.py` declara **três** rotinas diárias:

### 1. Curvas de Juros (ANBIMA)
**Frequência:** Todos os dias às 08:00 UTC (configurável via `CURVE_UPDATE_HOUR`).

Acessa a projeção da ANBIMA (`CZ-down.asp`) para capturar as taxas em múltiplos vértices (Pre e IPCA+). Como títulos podem vencer em *qualquer data* futura, os dados passam por **Interpolação Linear** que gera uma curva contínua em memória a partir da qual descontamos qualquer prazo.

### 2. Inflação e VNA IPCA+ (Banco Central — SGS 433)
**Frequência:** Todos os dias às 09:00 UTC (configurável via `IPCA_UPDATE_HOUR`).

Para títulos IPCA+ (NTN-B e NTN-B Principal), precisamos do **VNA** (Valor Nominal Atualizado), que cresce mensalmente com o IPCA. Este job busca as variações mensais do IPCA via **BCB SGS Série 433** e acumula o VNA base a partir do valor de referência de 1.000.

### 3. Fator Diário CDI/SELIC (Banco Central — SGS 12)
**Frequência:** Todos os dias às 08:30 UTC.

Para o **Tesouro Selic (LFT)** e **CDBs CDI-indexados**, precisamos do VNA SELIC e dos fatores diários do CDI. Este job busca os últimos 20 fatores diários via **BCB SGS Série 12** e os compõe sobre um valor âncora configurável (`LFT_VNA_ANCHOR` no `.env`) para calcular o VNA corrente do LFT com precisão de centavos.

---

## Monitoramento

| Endpoint | O que informa |
|---|---|
| `GET /health` | `using_fallback: true` indica que pelo menos uma API externa falhou |
| `GET /market/curves` | Curvas atuais em memória + hora da última atualização |
| `GET /market/vna` | VNA IPCA+ atual + série de inflação em cache |
