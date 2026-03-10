# Prompt para Migração - Parte 2: Frontend (finances-app)

A Parte 1 (implementação do backend na `pricing-engine`) foi concluída com sucesso. Agora, precisamos integrar a aplicação Next.js (`finances-app`) aos novos endpoints de mercado internacional, criptomoedas e câmbio.

## Contexto

A `pricing-engine` (rodando localmente em `http://localhost:8000`) foi expandida e hoje possui as seguintes novas rotas GET:
1. `/market/quote/us/{ticker}?quantity={x}` (ações e ETFs globais via TwelveData)
2. `/market/quote/crypto/{slug}?quantity={x}` (criptomoedas via CoinMarketCap)
3. `/market/currency/{from}/{to}?quantity={x}` (câmbio e moedas, ex: USD/BRL, via AwesomeAPI)

A `pricing-engine` cuida ativamente do rate limit (delay nas chamadas em background, retry exponencial para 5xx e cache fallback em 429). Ela retornará objetos JSON consistentes como: `{"price": 150.0, "updated_at": "...", "position_value": 300.0}`.

## O Que Fazer (Checklist de Implementação)

Na aplicação React/Next.js (`finances-app`):

1. **Atualizar o SDK de API / Hooks de Fetching:**
   - Adicionar os métodos/funções que chamarão os 3 novos endpoints da `pricing-engine`.
   - Pode-se utilizar o padrão de repositórios que já existe no projeto ou o React Query (caso já configurado).

2. **Refatorar os Cálculos Locais de Cotações:**
   - Identificar no dashboard/carteira onde as cotações internacionais (ex: `AAPL`), criptos (ex: `bitcoin`) e câmbio eram feitas de maneira local (hardcoded, chamadas a APIs instáveis do client, ou que possuíam delays visuais pesados).
   - Remover as regras lógicas antigas (e eventuais chamadas diretas de API do browser pro TwelveData ou CoinMarketCap).

3. **Substituir pelas Chamadas à Engine:**
   - Para **Ações US / Globais**, passe o ticker do ativo para `/market/quote/us/{ticker}` enviando a quantidade exata como _query parameter_.
   - Para **Criptomoedas**, certifique-se de mandar o identificador em formato _slug_ da CoinMarketCap (`/market/quote/crypto/bitcoin?quantity=0.5`).
   - Para posições em **Moeda Estrangeira**, passar `from=USD` e `to=BRL` (a base local da conta é em Real) para `/market/currency/USD/BRL`.

4. **Tratamento de Interface Visual:**
   - Como os componentes agora confiam em requisições de servidor externas à pricing-engine, verificar a interface de _Loading State_ (Spinners ou Skeletons).
   - Criar tratamento de fallback de interface caso a engine retorne status `500` por conta das APIs falharem sistematicamente nas várias tentativas na origem (Ex: exibir UI de "Cotação Indisponível" ou usar o "Preço de Custo" temporariamente).

5. **Testar os Tipos de Ativos Visuais (Iconografia/Flags):**
   - As cotações que chegam da API agora não bloqueiam mais por Rate Limit (devido a mecânica de fallback em cache da engine), então valide no frontend como as flags (Padrão US, BRL) e os ícones de Cripto ficam renderizados em grid completo de carregamento simultâneo.
