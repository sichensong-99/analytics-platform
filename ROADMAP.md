# Internal Analytics Platform — Roadmap

> Last updated: 2026-05-27
> Current phase: **Slice 1 complete · Awaiting `order_metafield` for replacement-exclusion rerun · Slice 2 starting**

---

## 🗺 Delivery Method — Vertical Slice (Decision 10)

The original plan was waterfall: build every ODS/DWD/DWS layer, then services,
then frontend. **Decision 10 replaced that with vertical slicing** — each slice
delivers one PBI page end-to-end (data source → Kimball model → metrics service
→ frontend portal) so Leader sees real output early and join-logic errors
surface immediately.
Phase 1 ✅ ── Phase 2A ✅ ──┐
│
▼
┌─────────────────────────────┐
│   Vertical Slices           │
│   each = one PBI page       │
│   end-to-end                │
├─────────────────────────────┤
│   Slice 1 ✅  Style × Channel│
│   Slice 2 🔜  Revenue        │
│   Slice 3 📋  Refunds        │
│   Slice 4 📋  ROAS           │
└─────────────────────────────┘
│
▼
Phase 4 (orchestration + DQ gates, designed)
│
▼
Phase 4.5 ⭐ Streaming (real-time anomaly, designed)
│
▼
Phase 5 (Redis + catalog + lineage)
│
▼
Phase 6 (deployment + docs + cost ROI)
│
▼
✅ Project complete → CV submission → Interview prep
**Total horizon**: 11-15 weeks (~3-4 months)

---

## Phase 1 — Portal MVP ✅

**Status**: Completed

- [x] Next.js + TypeScript + Tailwind scaffolding
- [x] JWT auth (httpOnly cookie, shared secret across services)
- [x] Dashboard list + detail pages
- [x] ECharts (line, bar)
- [x] CSV export
- [x] Mock data shaped to Data Contract schemas
- [x] Data Contract docs (Shopify, Triple Whale)

**Resume signal**: Full-stack delivery · Data Contract engineering discipline

---

## Phase 2A — Metrics Service Skeleton ✅

**Status**: Completed

- [x] FastAPI structure + uv dependency management
- [x] YAML metric definitions (`revenue_by_day` / `aov_by_day` /
      `roas_by_channel` / `ad_spend_by_day` baseline)
- [x] Metric versioning + changelog discipline
- [x] YAML loader + caching
- [x] JWT auth (shared secret with Next.js)
- [x] Mock Databricks client (swappable interface)
- [x] CORS + FastAPI auto docs (`/docs`)
- [x] Next.js refactor to consume FastAPI

**Resume signal**: Data Serving Layer · Metric Platform · Versioned Metrics

---

## Pre-Slice Preparation Tracks ✅

Originally planned as a parallel "wait for data" period. **All three tracks
completed** before / during Slice 1:

- [x] **Track 1** — PBI data source inventory → `docs/existing_data_inventory.md`
      (with §5.1 Style-channel page mapping)
- [x] **Track 2** — Target star schema → `docs/data_modeling/star_schema_ddl.sql`
      (now v2.0, synced to production tables)
- [x] **Track 3** — DQ framework skeleton → `metrics-service/data_quality/`
      (YAML-driven: not_null / unique / range / freshness)

---

## Slice 1 — Style × Channel Quantity ✅

**Status**: Completed 2026-05-27
**Duration**: ~9 days (Day 1-5 planned + Day 6-9 reconciliation iteration)
**PBI page replaced**: `Style-channel (quantity)`

### Deliverables
- [x] `fact_orders_line` Delta table — 9.97M rows, partitioned by ISO week
- [x] 3 conformed dimensions (`dim_date` 2,922 / `dim_channel` 23 / `dim_product` 36,680)
- [x] 4 PySpark notebooks (`01_build_dim_date` / `02_seed_dim_channel`
      / `03_build_dim_product` / `04_build_fact_orders_line`)
- [x] `quantity_by_style_channel_week` v1.2 YAML metric
      (net units, Decision 22 v3 semantics)
- [x] FastAPI metrics service live-connected to Databricks SQL Warehouse (OAuth U2M)
- [x] Next.js `style-channel-quantity` page wired to live API
- [x] Reconciliation tooling — Panoply BigQuery query + Databricks query
      + Python diff + Excel report
- [x] DDL synced to production tables (`star_schema_ddl.sql` v2.0)
- [x] Slice 1 completion summary (`docs/architecture/slice_1_completion_summary.md`)

### Quantified results
| Metric | Value |
|---|---|
| ETL row count (window) | 9,965,352 |
| TW join match rate | 99.72% |
| Channel DQ unmatched | 0.318% (PASS, baseline 0.15%) |
| Product DQ unmatched | 0.000% (PASS) |
| Reconciliation overall diff | **−1.51%** (< 2% trust gate ✓) |
| Reconciliation buckets | 221 (PASS 49.77% / WARN 29.86% / FAIL 20.36%) |
| Residual itemization | 100% (EXC 2,209 + refund 6,573 + cancel 803) |

### Architectural decisions locked
Decision 10 (Vertical Slice) · 11 (ISO 8601) · 12 (SCD1 YAGNI) · 13 (Schema-ETL decoupling) ·
14 (Meta-category explicit) · 15→21 (`channel_group` as roll-up hierarchy) · 16 (`is_paid` forward-looking) ·
17 (DST-aware timezone) · 18 (Multi-tier DQ SLO) · 19 (ERS dual-schema) ·
20 (Shared raw zone) · 22 v3 (`is_sales_attributable` + line-level refund netting).

### Open follow-up
- [ ] `order_metafield` arrives → rerun notebook 04 → activate `is_replacement_order`
      (predicted residual: −1.51% → ~−1.7%, still within 2% gate)
- [ ] Leader demo (script drafted in `docs/demo/leader_demo_script.md`)

**Resume signal**: Kimball star schema · Cross-source heterogeneous-type join ·
Last-touch attribution dedup via window function · Multi-tier DQ SLO ·
Reconciliation-driven model correction · Materialized business rules ·
Quantified legacy accuracy gap ·  DST-aware timezone (legacy bug correction)

---

## Slice 2 — Revenue page 🔜

**Status**: Next up after Leader demo feedback
**Estimated**: 5-7 days (faster than Slice 1 — fact/dim infra reused)

### Scope
- Migrate PBI revenue page semantics (gross revenue / net revenue / AOV by channel × week)
- Add `line_total` / `line_discount` measures to `fact_orders_line` (already in
  v1.1 DDL forward-looking design — no schema change needed)
- Optional: introduce order-grain `fact_orders` if channel × date aggregation
  benchmarks slow on line-grain (Kimball multi-grain modeling)

### Carry-over from Slice 1
- ✅ All 3 dimensions reused as conformed
- ✅ Reconciliation tooling reused with revenue SQL
- ✅ Frontend / FastAPI patterns reused

**Resume signal**: Conformed dimensions · Slice-to-slice marginal cost reduction ·
Multi-grain Kimball modeling (if order-grain fact added)

---

## Slice 3 — Refunds page 📋

**Estimated**: 7-10 days

### Scope
- Materialize legacy Panoply refund / replacement classification rules
  (18+ `tag_category` + 3-tier `Responsibility` Warehouse/Shipping/32D)
  as `dim_refund_reason` lookup tables
- Build refund-grain fact joining `order_line_refund` + parent `refund` table
- Replace ~200 lines of hardcoded CASE WHEN with YAML-maintained classification

**Resume signal**: Business rule lookup tables · Refund root-cause attribution model

---

## Slice 4 — ROAS page 📋

**Estimated**: 7-10 days

### Scope
- Add `fact_attribution_touchpoint` to ingest TW ad-spend data
- ROAS metric using `is_paid = TRUE` denominator (pre-encoded in `dim_channel`
  Slice 1 — Decision 16 pays off here)
- Channel-level paid-media performance dashboard

**Resume signal**: Multi-fact analytics · Forward-looking flag activation ·
Cross-fact metric construction

---

## Phase 4 — Workflows Orchestration + DQ Gates 📋

**Status**: Fully designed (`docs/architecture/phase4_orchestration_design.md`, ~750 lines)
**Estimated**: 5-7 days implementation

- [ ] Databricks Workflows DAG (ODS → DWD → DWS per slice)
- [ ] Retry policy + Slack/Email alerts + success digest
- [ ] DQ framework as pipeline tasks (DQ-as-Gate pattern)
- [ ] Staged migration: Full → Incremental load with `updated_at` watermark + 2-day lookback
- [ ] Idempotency + config-as-code

**Decisions already locked**: Workflows over Airflow (Decision 5, with
decision-flip conditions documented for interview).

**Resume signal**: Orchestration · DQ-as-Gate · Staged migration with watermark ·
Multi-channel alerting

---

## Phase 4.5 — Streaming Module ⭐ 📋

**Status**: Fully designed (`docs/streaming_module_plan.md`)
**Estimated**: 5-7 days
**Business scope**: Real-time channel anomaly monitoring (ROAS drop)

### P0 (3 days)
- [ ] Mock data generator (orders + ads streams)
- [ ] Auto Loader streaming notebook
- [ ] 5-min sliding window
- [ ] Channel-level metrics
- [ ] Simple anomaly rule

### P1 (additional 2-3 days) ⭐ Don't skip
- [ ] Stream-stream join
- [ ] Checkpoint + Exactly-once semantics
- [ ] Watermark + late-arriving data handling
- [ ] `dropDuplicatesWithinWatermark`
- [ ] Stream-batch unified via Delta Lake

**Resume signal**: Structured Streaming · Watermark · Exactly-once · Stream-batch unification

---

## Phase 5 — Platform Capabilities 📋

**Estimated**: 1-2 weeks

- [ ] Redis cache layer in metrics service (quantified hit rate + cost saving)
- [ ] Metrics Catalog page (all metrics + version + owner + lineage)
- [ ] Lineage visualization (ECharts graph)
- [ ] Cache impact quantification (query latency before/after)

**Resume signal**: Platform engineering · Performance optimization · Lineage tracking

---

## Phase 6 — Deployment + ROI 📋

**Estimated**: 1 week

- [ ] Deployment (Vercel frontend / company server backend)
- [ ] Complete documentation (architecture, API, user guide, runbook)
- [ ] Cost analysis (PBI savings vs Databricks compute + ROI)
- [ ] Usage stats (DAU, query volume, hot metrics)
- [ ] Tech blog post
- [ ] GitHub README polish (architecture diagram, screenshots, demo video)

**Resume signal**: Quantified outcomes · Project operation discipline · Tech writing

---

## Final Resume Draft (post-Phase 6)

> **Internal Data Analytics Platform / Lead Designer & Developer** | 2026.04 – 2026.07
>
> Replaced Power BI Service, reducing team subscription cost by $X/year and serving N team members.
>
> **Data Architecture**
> - Designed and delivered Kimball star schema on Databricks Lakehouse via
>   **vertical-slice methodology** (4 slices, one PBI page each end-to-end)
> - Integrated Shopify (orders / refunds / replacements), Triple Whale
>   (attribution), and external ERS / freight data into the Lakehouse,
>   processing ~10M order lines and ~25M TW attribution events
> - Implemented business-rule-materialization pattern
>   (`is_sales_attributable` boolean) replacing scattered legacy WHERE filters
> - Defined Data Contracts before ingestion, set cross-team schema, quality, SLA expectations
>
> **Data Quality & Reconciliation**
> - Built quantitative reconciliation methodology vs legacy Panoply pipeline,
>   achieving **−1.51% diff with fully itemized residual attribution**,
>   identifying and correcting 3 legacy accuracy gaps (DST timezone drift,
>   22% refund undercoverage, cancelled-orders-counted-as-sales)
> - Designed multi-tier DQ SLO (PASS / WARN / FAIL) calibrated against
>   empirical 0.15% baseline, avoiding alert fatigue
> - Implemented DQ-as-Gate pattern halting pipeline before bad data writes
>
> **Metrics Service Layer**
> - Implemented unified metrics service decoupling metric definition from consumption
> - YAML-driven metric DSL — new metrics with zero code changes
> - **Versioned metrics** with breaking-change annotation for semantic shifts
> - FastAPI REST API + Redis cache reducing Databricks query cost ~70%
>
> **Data Governance**
> - Metric lineage tracking & visualization for impact analysis
> - YAML-driven data quality framework (completeness / uniqueness / freshness)
> - Databricks Workflows orchestration with retry, alerting, dependency management
>
> **Stream Processing**
> - Databricks Structured Streaming + Auto Loader for real-time channel anomaly monitoring
> - Stream-stream join · Watermark late-data handling · Exactly-once semantics
> - Stream-batch unified storage via Delta Lake
>
> **Frontend**
> - Next.js + ECharts self-service portal — dashboard browsing, metric catalog, CSV export
>
> **Stack**: Databricks · PySpark · Spark Structured Streaming · Delta Lake ·
> FastAPI · Next.js · Redis · ECharts · YAML