# Amazon Shipment Ingestion — Design Doc

> **Status**: Design phase
> **Author**: Sia
> **Created**: 2026-05-27
> **Driving need**: Leader wants Amazon shipment data (currently in legacy
> Panoply) on the new platform, sourced directly via Amazon's API.
> **Volume**: Low (a few hundred to few thousand records/week).
> **Cadence**: Weekly (Monday). Implementation: scheduled, NOT manual.

---

## 1. Why this matters

Amazon shipment data shares **no join key** with Shopify or Triple Whale data
in scope for Slices 1-4 — it's an independent business stream (B2B wholesale
shipments). This is therefore NOT integrated into `fact_orders_line`; it lives
as a self-contained domain on the same platform.

The strategic value of putting it on the platform anyway:
1. **Platform extensibility** — demonstrate the platform can absorb new
   sources by following the same patterns, without re-architecture.
2. **Ingestion pattern completion** — Slices 1-4 consume data ingested by
   other teams (Fivetran, TW pipeline owner). This task delivers an
   ingestion pipeline OWNED by the platform itself, closing the loop on
   "end-to-end".

---

## 2. Source contract

| Attribute | Value |
|---|---|
| Source system | Amazon Seller Partner API (SP-API) |
| Endpoint | `/fba/inventory/v1/summaries` and `/fba/inbound/v0/shipments` (TBD per Leader's data definition) |
| Auth | OAuth 2.0 LWA (Login With Amazon) — refresh token |
| Rate limit | (TBD — Amazon publishes per-endpoint) |
| Volume | ~hundreds to few thousands of records / week |
| Freshness SLA | T+1 day acceptable (run Monday morning) |

---

## 3. Architecture
Amazon SP-API
│  HTTPS, OAuth bearer
▼
Ingestion Notebook  (Databricks Workflows weekly schedule, Mon 06:00 ET)
│  • Retry with exponential backoff
│  • Rate-limit aware (token bucket)
│  • Pagination handling
│  • Idempotent write (overwrite by run_date partition)
▼
Bronze: amazon_shipment_raw  (Delta, JSON-as-string + ingest metadata)
│  • Schema-on-read, full audit trail
│  • Retention: 90 days (replay window)
▼
Silver: amazon_shipment      (Delta, normalized typed schema)
│  • Field-by-field cast and validate
│  • DQ gates: not_null on shipment_id, range on quantity
▼
Gold: amazon_shipment_weekly (Delta, business-grade aggregate)
│  • Whatever Leader wants displayed
▼
(Future) Metrics service exposes via separate YAML metric definitions
---

## 4. Decisions

### Decision A1: Storage — Databricks (Bronze/Silver/Gold), NOT Neon
- ✅ Same platform → unified governance, lineage, DQ framework
- ✅ Demonstrates platform extensibility
- ✅ Medallion architecture is industry-standard, resume-relevant
- ✅ Cheap for this volume (Delta on object storage)
- ❌ Slight overkill for a few thousand records/week, but the **pattern** is
   the deliverable, not the volume

### Decision A2: Scheduling — Databricks Workflows, NOT manual
- ✅ Reuses Phase 4 orchestration design — get a head start on Phase 4
- ✅ Removes the "Sia must remember every Monday" failure mode
- ✅ Failure alerting + retry come for free
- ❌ No real downside

### Decision A3: Schedule cadence — weekly cron, NOT event-driven
- Leader's SLA = weekly Monday. No business reason to do more.
- Event-driven (e.g. webhook) is overengineering when source doesn't emit events.

### Decision A4: Bronze retention 90 days
- Allows 12-week replay window for backfill / bug fix
- Volume is tiny, storage cost negligible
- Industry default for raw-zone retention

### Decision A5: NOT integrated with `fact_orders_line`
- Amazon shipments share no business key with Shopify orders
- Forcing a join would create a fake fact relationship
- Kept as an independent business domain — Slices 5+ may consume it standalone

### Decision A6: Reuse existing YAML DQ framework
- Track 3 framework gets its **second production application**
- Validates the framework is generic, not slice-1-specific
- Resume signal: "Framework reuse across domains"

---

## 5. Failure & operations

| Failure | Handling |
|---|---|
| Amazon API 429 (rate limit) | Exponential backoff, max 5 retries, then alert |
| Amazon API 5xx | Retry x3, then alert |
| OAuth token expired | Auto-refresh via refresh token; if refresh fails, alert |
| Schema drift (new field) | Bronze stores JSON-as-string, tolerates new fields. Silver explicit cast catches missing/renamed required fields → fail loudly. |
| DQ FAIL on Silver | Pipeline halts; Bronze data preserved; alert to Sia |
| Partial week | Idempotent overwrite by `run_date` partition — re-run safely. |

Alerts: Slack channel (same as Phase 4 design).

---

## 6. Resume signals from this task

- API Ingestion · OAuth 2.0 · Rate-limit-aware client
- Medallion Bronze/Silver/Gold architecture
- Idempotent pipeline with partition-overwrite
- Schedule orchestration (Databricks Workflows)
- Schema-on-read raw zone with schema-on-write Silver normalization
- Framework reuse (YAML DQ framework second domain)
- Platform extensibility — new source absorbed without re-architecture
- Failure modes designed (retry, backoff, alerting, replay window)

---

## 7. Out of scope

- Metrics-service exposure (deferred until Leader needs frontend display)
- Frontend page (same)
- Join with Shopify / TW (no business key)
- Real-time streaming (weekly cadence — not needed)