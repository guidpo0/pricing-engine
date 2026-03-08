# Background Jobs & Data Refresh

One of the most critical characteristics of this engine is that it **does not** perform slow HTTP requests to external APIs on the fly when pricing an asset.

To guarantee **sub-millisecond latency** across all pricing endpoints, the necessary market data is kept in local RAM caches, continuously refreshed in the background.

---

## Scheduler Lifecycle

The application integrates `APScheduler` using its `AsyncIOScheduler` executor, which binds directly to the FastAPI `asyncio` Event Loop without thread-blocking.

1. **Startup (Lifespan):** During Uvicorn initialization, FastAPI fires its `startup` hooks. At this point, the engine concurrently fetches live data from **ANBIMA** (Yield Curves) and the **Central Bank** (IPCA, CDI factor) via `asyncio.gather`.

   > **What if an external API is down during boot?**
   > Each service has hardcoded fallback constants (`_FALLBACK_PRE_CURVE`, `_FALLBACK_LFT_VNA`, etc.) that are loaded into RAM if the external fetch fails. The engine logs a warning and boots successfully regardless.

2. **Scheduling:** After populating the RAM caches, `APScheduler` takes over in the background at configured hours, silently replacing stale data with fresh rates as external services recover.

3. **Shutdown (Lifespan):** Clean termination signals trigger the Scheduler to stop gracefully.

---

## The Jobs

The file `app/jobs/update_market_data.py` schedules **three** daily routines:

### 1. Yield Curve Refresh (ANBIMA)
**Frequency:** Every day at 08:00 UTC (configurable via `CURVE_UPDATE_HOUR`).

Fetches the current ANBIMA yield curve projection at multiple vertices (Pre and IPCA+). Because bonds can mature on *any arbitrary future date*, rates are passed through **Linear Interpolation** to produce a continuous curve in memory.

### 2. Inflation & IPCA+ VNA (Central Bank — SGS 433)
**Frequency:** Every day at 09:00 UTC (configurable via `IPCA_UPDATE_HOUR`).

For IPCA+ bonds (NTN-B and NTN-B Principal), we need the **VNA** (Valor Nominal Atualizado), which grows monthly with inflation. This job fetches monthly IPCA readings via **BCB SGS Series 433** and accumulates the VNA from a reference base of 1,000.

### 3. CDI/SELIC Daily Factor (Central Bank — SGS 12)
**Frequency:** Every day at 08:30 UTC.

For the **Tesouro Selic (LFT)** and **CDI-indexed CDBs**, we need the daily SELIC/CDI compounding factor. This job fetches the last 20 daily factors via **BCB SGS Series 12** and compounds them over a configurable anchor value (`LFT_VNA_ANCHOR` in `.env`) to compute the current LFT VNA with cent-level precision.

---

## Monitoring

| Endpoint | What it shows |
|---|---|
| `GET /health` | `using_fallback: true` means at least one external API failed |
| `GET /market/curves` | Live curves in memory + last update time |
| `GET /market/vna` | Current IPCA+ VNA + cached inflation series |
