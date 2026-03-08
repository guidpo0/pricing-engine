# Decisões de Arquitetura (ADR)

Este documento registra as principais decisões arquiteturais tomadas durante o design do **Pricing Engine do Tesouro Direto**, bem como as motivações técnicas por trás de cada escolha.

---

## 1. Zero Banco de Dados (In-Memory Cache)

O sistema **não utiliza um banco de dados relacional (SQL) ou NoSQL**. Todos os dados de mercado necessários para o funcionamento das fórmulas (Curvas de Juros e VNA/Inflação) são mantidos diretamente na memória RAM da aplicação.

### Por que?
- **Desempenho Extremo (Milisegundos/Nanossegundos):** Um *pricing engine* é frequentemente chamado em *batch* (ex: reprecificar uma carteira com centenas de posições de diferentes usuários). Se houvesse um banco de dados, a API gastaria entre 5ms e 10ms só em tráfego de rede (I/O, TCP/IP) para consultar as taxas de cada requisição. Na memória RAM local, a leitura é praticamente instantânea, tornando a API extremamente rápida.
- **Efemeridade do Dado:** As taxas de juros (Yield Curves) que importam para a marcação a mercado ("Mark-to-Market") mudam apenas uma ou duas vezes por dia. Quando o dia vira, as antigas tornam-se inúteis para novos cálculos no presente. Não há necessidade sistêmica neste serviço específico de manter o histórico perpétuo das curvas em disco rígido.
- **Tamanho Microscópico:** A curva ANBIMA possui em média cerca de 20 vértices (pontos). Guardar isso não consome nem 1 MB de RAM. A complexidade e o custo financeiro de manter e gerenciar um banco de dados (como RDS PostgreSQL ou Redis) para salvar 20 linhas não se justificam frente aos ganhos.

---

## 2. Padrão de Resiliência: Graceful Degradation (Degradação Suave)

O código possui constantes de *fallback* "mockadas" (`_FALLBACK_PRE_CURVE`, `_FALLBACK_IPCA_CURVE`) que são enviadas para a RAM caso as chamadas de API externas falhem.

### Por que?
- Se você for realizar o _deploy_ da aplicação (ou reiniciar o pod no Kubernetes) exatamente em um momento de instabilidade nos servidores governamentais (SGS BCB ou ANBIMA), a aplicação poderia simplesmente "crashar" e não subir, paralisando a precificação de todos os seus clientes.
- Nós priorizamos a **Disponibilidade** em detrimento de uma exatidão momentânea (Teorema CAP).
- **Graceful Degradation:** A API loga um erro avisando da indisponibilidade, sobe usando os dados do dia anterior (fallback), e permite que as carteiras continuem sendo precificadas. Enquanto isso, um _Job em background_ continuará tentando, repetidas vezes, bater nas APIs externas, fazendo a substituição silenciosa e automática assim que o serviço do governo normalizar.
- Essa condição pode ser monitorada pelos times de infraestrutura em tempo real acessando a rota `/health` e observando a chave de retorno `"using_fallback": true`.

---

## 3. Worker Assíncrono no mesmo Loop (APScheduler vs Celery)

A requisição e atualização diária de dados acontece puramente em `asyncio` por meio da biblioteca `APScheduler`. Não usamos bibliotecas "pesadas" de controle de fila e workers separados (como o `Celery` + `RabbitMQ/Redis`).

### Por que?
- Como temos poucas tarefas (atualizar duas variáveis a cada 24 horas), levantar processos separados (workers) e instâncias de mensageria traria uma dor de cabeça imensa de infraestrutura (DevOps) apenas para rodar dois métodos soltos ao dia.
- O `APScheduler` com o executor `AsyncIOScheduler` se integra perfeitamente ao Event Loop nativo do FastAPI (`uvicorn`). Quando é hora do job rodar, ele compartilha sutilmente o processador com as requisições HTTP, de forma assíncrona (IO-bound), sem bloquear a sua aplicação.
