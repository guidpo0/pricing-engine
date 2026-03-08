# Architecture Decisions (ADR)

This document tracks and explains the core architectural patterns and design decisions made for the **Tesouro Direto Pricing Engine**, alongside their technical motivations.

---

## 1. Zero Database (In-Memory Caching)

The system **does not use any SQL or NoSQL database**. All external market data required to power the pricing formulas (Yield Curves and IPCA/VNA) are persisted directly into the application's local RAM.

### Why?
- **Extreme Performance (Sub-millisecond latency):** A *pricing engine* is often hit by massive batch requests (e.g., evaluating a user's entire portfolio holding hundreds of bonds). If a database was involved, every calculation would require crossing the network (I/O, TCP/IP overhead) costing ~5ms+ per query. Storing an array array in local RAM reduces this overhead to virtually zero, enabling ultra-fast computations.
- **Ephemeral Data Nature:** Prevailing interest rates used for present-time Mark-to-Market valuation typically change once or twice a day. Yesterday's rates hold no value for today's mark-to-market. There is no systemic requirement in this specific service bounded context to persist historical rates on a hard drive.
- **Microscopic Payload Size:** An ANBIMA yield curve usually holds around 20 vertices (tenor/rate pairs). Holding this in memory consumes less than 1 MB of RAM footprint. The DevOps burden and financial cost of provisioning and maintaining an external database (like RDS PostgreSQL or Redis cluster) merely to hold 20 rows is highly unjustified.

---

## 2. Resilience Pattern: Graceful Degradation (Fallbacks)

The codebase holds hardcoded dummy/mock constants (`_FALLBACK_PRE_CURVE`, `_FALLBACK_IPCA_CURVE`) pushed to RAM during initialization if the network requests to ANBIMA/BCB fail to respond.

### Why?
- Suppose you need to deploy a new version (or Kubernetes restarts the Pod) precisely when the Brazilian Central Bank's SGS API is throwing a `504 Gateway Timeout`. Without a fallback strategy, the engine would crash on boot, effectively creating an outage for all downstream systems trying to price portfolios.
- We prioritize **Availability** over absolute, to-the-second exactness (in line with the CAP theorem).
- **Graceful Degradation:** The API emits a loud warning log about the failure, boots using yesterday's hardcoded data (fallback), and seamlessly continues pricing bounds for clients. Meanwhile, the background scheduler takes over and repeatedly attempts to hit the government APIs. Upon stabilization, the backend silently overwrites the RAM cache with live data.
- Ops teams can passively monitor this state by fetching the `/health` endpoint and checking `"using_fallback": true`.

---

## 3. Co-located Async Background Workers (APScheduler vs Celery)

The periodic daily data fetching runs via pure `asyncio` routines scheduled by `APScheduler`, rather than external heavy-weight queue managers like `Celery` backed by `RabbitMQ` or `Redis`.

### Why?
- Given that the workload involves running extremely lightweight network IO tasks only 2 or 3 times per 24 hours, spinning up dedicated worker processes and message brokers introduces a staggering level of operational overhead (Ops Tax) for zero tangible benefits.
- Using `APScheduler` combined with `AsyncIOScheduler` acts identically to a cron job but binds directly and safely to the FastAPI (`uvicorn`) concurrent Event Loop. When triggered, it non-blockingly multiplexes its network requests alongside incoming HTTP requests, never stalling the main API layer.
