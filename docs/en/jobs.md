# Background Jobs & Data Refresh

The engine **does not** perform slow HTTP requests to external APIs on the fly when pricing an asset.

To guarantee **sub-millisecond latency**, the necessary market data is kept in local RAM caches.

---

## Data Architecture

### 1. Startup (Lifespan)

During Uvicorn initialization, the engine loads cached data from PostgreSQL into RAM.

> **What if no cached data exists?**
> Each service has hardcoded fallback constants (`_FALLBACK_PRE_CURVE`, `_FALLBACK_LFT_VNA`, etc.) that are loaded into RAM. The engine logs a warning and boots successfully.

### 2. Data Updates

Data updates are **not** performed by internal background jobs. Instead, a **separate external cron job** (GitHub Actions) calls the `/investments/update-cache` endpoint periodically.

This approach:

- Avoids rate limiting from external APIs
- Keeps the API responsive during data fetches
- Allows independent scaling of data updates from API serving

### 3. Runtime Behavior

On each request, the API:

1. First tries to use the in-memory cache (fastest)
2. Falls back to PostgreSQL history if memory cache is stale/missing
3. Fetches from external API only if no cached data exists, and saves to PostgreSQL

---

## The `/investments/update-cache` Endpoint

This endpoint is called by the external cron job to update all market data:

```bash
curl -X POST https://your-api.com/investments/update-cache \
  -H "X-API-Key: your-token"
```

It updates:

- **Yield Curves** (ANBIMA)
- **Inflation/IPCA+ VNA** (Central Bank)
- **CDI/SELIC rates** (Central Bank)
- **Stock quotes** (Brazil, US)
- **Crypto quotes**
- **Currency rates**

All data is saved to PostgreSQL as historical records (INSERT only, never UPDATE/DELETE).

---

## Monitoring

| Endpoint                          | What it shows                                                 |
| --------------------------------- | ------------------------------------------------------------- |
| `GET /health`                     | `using_fallback: true` means at least one external API failed |
| `GET /market/curves`              | Live curves in memory + last update time                      |
| `GET /market/vna`                 | Current IPCA+ VNA + cached inflation series                   |
| `GET /investments/history-status` | Last data update timestamp from PostgreSQL                    |
