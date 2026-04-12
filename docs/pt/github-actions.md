# Configuração do GitHub Actions

Este documento explica como configurar o workflow do GitHub Actions para atualizar dados de investimentos.

## Visão Geral

O workflow (`update-investments.yml`) atualiza automaticamente os dados de mercado a cada 4 horas:

1. **Health Check** - Acorda o container do Render (se estiver dormindo)
2. **History Status** - Verifica o status atual dos dados
3. **Update Cache** - Chama `/investments/update-cache` para buscar e salvar todos os dados
4. **Verify Update** - Confirma que os dados foram salvos no PostgreSQL

## Configuração Necessária

### 1. Variáveis do Repositório

Vá para o repositório no GitHub → Settings → Variables → Actions:

| Variável       | Valor                          | Descrição                |
| -------------- | ------------------------------ | ------------------------ |
| `API_BASE_URL` | `https://seu-app.onrender.com` | URL do seu app no Render |

### 2. Secrets do Repositório

Vá para o repositório no GitHub → Settings → Secrets → Actions:

| Secret           | Valor                                     | Descrição                                      |
| ---------------- | ----------------------------------------- | ---------------------------------------------- |
| `API_AUTH_TOKEN` | O valor de `API_AUTH_TOKEN` do seu `.env` | Token para autenticar com a Pricing Engine API |

### 3. Configuração do Render

Certifique-se de que seu app no Render tem:

- **Environment Variables:**
  - `API_AUTH_TOKEN` - Deve ser igual ao secret acima
  - `DATABASE_URL` - String de conexão do PostgreSQL
- **Health Check:** Configure `/health` como endpoint de health check

## Visibilidade da Execução

Cada execução do workflow fornece logs detalhados para cada etapa:

### Etapa 1: Health Check

```
📡 STEP 1: Health Check (Wake Up Container)
💤 Attempting to wake up Render container...
📊 HTTP Status Code: 200
📦 Response Body:
{
  "status": "ok",
  "curves_last_updated": "2026-04-12T08:00:00Z",
  "vna_last_updated": "2026-04-12T09:00:00Z",
  "curves_using_fallback": false,
  "vna_using_fallback": false
}
✅ Container is awake and healthy!
```

### Etapa 2: History Status

```
📜 STEP 2: Check History Status
📊 Querying /investments/history-status...
✅ Historical data exists
   • Last Updated: 2026-04-12T10:00:00Z
```

### Etapa 3: Update Cache

```
🔄 STEP 3: Update All Investments
📡 Calling POST /investments/update-cache...
📈 Update Results:
   • Overall Status: success
   • Updated At: 2026-04-12T14:00:00Z

📊 Individual Updates:
   • Yield Curves: success
   • Inflation/VNA: success
   • BR Stocks (15 updated): success
   • US Stocks (10 updated): success
   • Crypto (5 updated): success
   • Currencies (8 updated): success
```

## Execução Manual

Você pode acionar o workflow manualmente pela aba GitHub Actions:

1. Vá para a aba **Actions**
2. Selecione **Update Investments Data**
3. Clique em **Run workflow**
4. Opcionalmente habilite **Force wakeup**

## Schedule do Cron

O workflow roda a cada 4 horas:

- 00:00 UTC
- 04:00 UTC
- 08:00 UTC
- 12:00 UTC
- 16:00 UTC
- 20:00 UTC

Para mudar o schedule, edite a expressão cron em `.github/workflows/update-investments.yml`:

```yaml
on:
  schedule:
    - cron: "0 */4 * * *" # A cada 4 horas
```

## Troubleshooting

### Container Não Acorda

- Verifique o status do app no dashboard do Render
- Teste o health check endpoint: `curl https://seu-app.onrender.com/health`

### Autenticação Falhou (401)

- Verifique se o secret `API_AUTH_TOKEN` é igual ao do Render
- Check se o token está configurado corretamente nas variáveis de ambiente do Render

### Update Falhou

- Verifique os logs do workflow para detalhes específicos do erro
- Verifique se a conexão PostgreSQL está funcionando
- Check os logs da API no dashboard do Render

### Rate Limiting

- O workflow inclui delays entre requests para respeitar rate limits
- Se você ver erros 429, considere reduzir o número de tickers rastreados ou aumentar os delays
