# Background Jobs & Data Refresh

One of the most critical characteristics of this engine is that it **does not** perform slow HTTP requests to external APIs on the fly when pricing a bond.

To guarantee **sub-millisecond latency** across the pricing (`/bonds/price`) and valuation (`/portfolio/value`) endpoints, the necessary market data curves are kept in local RAM caches that are constantly hydrated in the background.

---

## Scheduler Lifecycle

The application integrates `APScheduler` using its `AsyncIOScheduler` executor. This is the optimal design choice because it binds directly to the FastAPI `asyncio` Event Loop without thread-blocking.

1. **Startup (Lifespan):** During Uvicorn initialization, FastAPI fires its `startup` hooks. At this exact moment, the engine synchronously fetches the live data from **ANBIMA** (Yield Curves) and the **Central Bank** (IPCA). If the external APIs are down during pod startup, the engine will gracefully failover to hardcoded disk-based fallback constants (`curve_service.py` and `inflation_service.py`) and boot successfully anyway.
2. **Scheduling:** After populating the RAM caches, `APScheduler` takes over in the background.
3. **Shutdown (Lifespan):** Clean termination signals trigger the Scheduler to shut down its pending coroutines gracefully.

---

## The Actual Jobs

The file `app/jobs/update_market_data.py` schedules the two main daily routines:

### 1. Yield Curve Refresh (ANBIMA)
**Frequency**: Everyday at 08:00 AM and 14:00 PM (Configurable via `.env` variable `JOB_UPDATE_CURVES_HOUR`).

This job requests the current projection from ANBIMA to capture prevailing rates at distinct tenors (vertices). Because retail bonds can mature on *any* arbitrary future date, the fetched nodes pass through a mathematical **Flat-Forward Linear Interpolation**. This interpolation yields a perfectly continuous yield curve in memory from which we can pull rates for any exact 252-business-day timeframe.

### 2. Inflation & SELIC Refresh (Brazilian Central Bank)
**Frequency**: Everyday at 09:00 AM.

For Post-Fixed bonds like **Tesouro Selic** and **Tesouro IPCA+**, the yield curve alone isn't enough. We must calculate the current VNA (Valor Nominal Atualizado / Updated Nominal Value).
This job hits the **BCB SGS API** to fetch:
- **SGS 433 (IPCA):** Downloads inflation time-series to project the IPCA variations since the standard anchor date (the 15th of the month).
- **SGS 11 (SELIC):** Downloads the target SELIC and the cumulative daily effective rate, mandatory for discounting `LFT` bonds.
