# Jobs e Atualização de Dados

Um dos pontos mais críticos do sistema é não depender de requisições lentas em tempo real ("*on-the-fly*") para serviços externos na hora de precificar um título.

Para garantir **latência de milissegundos** em todos os endpoints (`/bonds/price` e `/portfolio/value`), os dados de mercado necessários são mantidos na RAM através de um cache local, que é constantemente hidratado em pano de fundo.

---

## Ciclo de Vida do Scheduler

A aplicação utiliza a biblioteca `APScheduler` rodando o executor `AsyncIOScheduler`. Ele foi escolhido por ser nativo do `asyncio` e não bloquear a única thread do _Event Loop_ do FastAPI.

1. **Startup (Lifespan):** Durante a inicialização do Uvicorn, o FastAPI dispara os eventos de `startup`. Neste momento, a engine realiza uma primeira busca síncrona/esperada na **ANBIMA** (Curvas de Juros) e no **Banco Central** (IPCA).
   > **E se a API externa falhar ou estiver fora do ar no momento do boot?**
   > Para garantir que a nossa engine de precificação *nunca* deixe de subir por culpa de instabilidades em servidores do governo/ANBIMA, existem dados estáticos (mockados/hardcoded) definidos nos arquivos `curve_service.py` e `inflation_service.py` (chamados de `_FALLBACK_IPCA_CURVE`, etc).
   > O sistema vai logar um *Warning*, carregar essas variáveis fixas na RAM e subir a API normalmente.
2. **Escalonamento:** Após popular a RAM (seja com os dados oficiais da internet, ou com os dados de fallback), o `APScheduler` entra em ação, rodando em background no loop assíncrono. **Nas horas programadas (ex: 08:00, 09:00, 14:00), ele vai novamente tentar bater nas APIs externas.** Assim que a internet/API externa voltar à vida, ele sobrescreve os dados em cache com as taxas atualizadas.
3. **Shutdown (Lifespan):** O encerramento limpo da aplicação envia o sinal para a thread do Scheduler parar graciosamente as pendências.

---

## Os Tarefeiros (Jobs)

O arquivo `app/jobs/update_market_data.py` declara duas rotinas diárias principais:

### 1. Atualização da Curva de Juros (ANBIMA)
**Frequência**: Todo dia às 08:00 AM e 14:00 PM (Configurável via variável `.env` `JOB_UPDATE_CURVES_HOUR`).

Este Job acessa a projeção atual da ANBIMA para capturar as taxas em vários vértices (vencimentos). Como títulos podem vencer em *qualquer data* do futuro, os dados passam por uma **Interpolação Linear Flat-Forward** matemática. A interpolação gera uma curva contínua perfeita de juros na memória a partir da qual podemos descontar os fluxos de caixa de qualquer prazo (em dias úteis exatos de 252). 

### 2. Atualização de Inflação e SELIC (Banco Central do Brasil)
**Frequência**: Todo dia às 09:00 AM.

Para títulos Pós-Fixados como o **Tesouro Selic** e **Tesouro IPCA+**, apenas a curva de juros não é suficiente. Precisamos saber o VNA (Valor Nominal Atualizado).
Este job realiza as seguintes coletas via a **API SGS do Banco Central**:
- **SGS 433 (IPCA):** Busca as séries temporais desde o último VNA padrão (Todo dia 15). Todo Tesouro IPCA+ possui um VNA projetado retroativamente.
- **SGS 11 (SELIC):** Busca a Meta SELIC e efetivação acumulada diária, imprescindível pra descontar os títulos `LFT`.
