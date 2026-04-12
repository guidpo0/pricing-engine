# Architecture Decisions (ADR)

This document tracks and explains the core architectural patterns and design decisions made for the **Tesouro Direto Pricing Engine**, alongside their technical motivations.

---

## 1. Hybrid Storage: PostgreSQL + In-Memory Cache

The system uses **PostgreSQL as persistent historical storage** and **in-memory RAM** for active pricing calculations.

### Why PostgreSQL?

- **Persistent History:** Unlike ephemeral in-memory data, PostgreSQL survives container restarts (important on Render free tier where containers sleep after 15 minutes).
- **External Cron Jobs:** Data updates happen via a separate external cron job (GitHub Actions), avoiding rate limiting issues.
- **Historical Analysis:** Having historical data enables future features like price charts and trend analysis.

### Why In-Memory Cache?

- **Sub-millisecond Latency:** Pricing endpoints need ultra-fast access to yield curves and VNA data.
- **Read Pattern:** Most requests are reads (pricing calculations), with rare writes (external cron job).

### Data Flow

1. External cron job calls `/investments/update-cache` → data saved to PostgreSQL
2. On API startup, data loaded from PostgreSQL to RAM
3. On each pricing request, in-memory cache is used first
4. If cache is stale/missing, PostgreSQL is queried
5. If PostgreSQL is empty, external API is called (and result saved to PostgreSQL)

---

## 2. Resilience Pattern: Graceful Degradation (Fallbacks)

The codebase holds hardcoded dummy/mock constants (`_FALLBACK_PRE_CURVE`, `_FALLBACK_IPCA_CURVE`) pushed to RAM during initialization if the network requests to ANBIMA/BCB fail to respond.

### Why?

- Suppose you need to deploy a new version when the Brazilian Central Bank's SGS API is throwing a `504 Gateway Timeout`. Without a fallback strategy, the engine would crash on boot.
- We prioritize **Availability** over absolute, to-the-second exactness.
- **Graceful Degradation:** The API emits a warning log about the failure, boots using fallback data, and continues pricing bonds for clients.
- Ops teams can monitor this state by fetching the `/health` endpoint and checking `"using_fallback": true`.

---

## 3. External Cron Jobs vs Internal Workers

Data updates are performed by a **separate external cron job** (GitHub Actions), not by internal background workers.

### Why?

- **Avoid Rate Limiting:** Internal workers calling external APIs on every request caused rate limit issues with AwesomeAPI.
- **Separation of Concerns:** API servers stay responsive; data fetching is decoupled.
- **Simplicity:** No need for APScheduler or Celery-like complexity for simple periodic tasks.
- **Scalability:** External cron can be scaled independently from API servers.

### Implementation

- GitHub Actions workflow runs on a schedule (e.g., every 4 hours)
- Calls `POST /investments/update-cache` endpoint with API key
- All data is saved as INSERT-only records in PostgreSQL (never UPDATE/DELETE)
