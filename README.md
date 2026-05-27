# Internal Analytics Platform

> End-to-end data platform replacing Power BI Service for the 32 Degrees ecom
> team — ingests multi-source data into a Lakehouse, serves governed metrics
> through a versioned API, and surfaces them in a self-service web portal.

![status](https://img.shields.io/badge/status-Slice%201%20complete-brightgreen)
![stack](https://img.shields.io/badge/stack-Databricks%20%7C%20FastAPI%20%7C%20Next.js-blue)
![reconciliation](https://img.shields.io/badge/Slice%201%20reconciliation-%E2%88%921.51%25-brightgreen)
![scale](https://img.shields.io/badge/scale-~10M%20order%20lines-informational)

---

## Architecture
Next.js portal (dashboards · metrics catalog · lineage UI)
↓ HTTP + JWT
FastAPI metrics service (Redis cache · YAML metric layer · query binding)
↓ SQL
Databricks Lakehouse (Kimball star schema · Delta Lake · DST-aware)
↑ Auto Loader + Structured Streaming (Phase 4.5)
Shopify · Triple Whale · ERS master · freight CSVs
↑ Orchestrate
Databricks Workflows (DAG · multi-tier DQ gates · alerts)
---

## Slice 1 — Style × Channel Quantity ✅

End-to-end migration of the legacy PBI `Style-channel (quantity)` page,
delivered as the first vertical slice of the new platform.

| Result | Value |
|---|---|
| Order lines processed (ETL window) | **9.97M** |
| Shopify order_line (full table) | 44.67M |
| TW attribution_order_click (full table) | 25.26M |
| TW cross-source join match rate | 99.72% |
| Channel DQ unmatched | 0.318% (PASS) |
| Product DQ unmatched | 0.000% (PASS) |
| Reconciliation vs Panoply legacy | **−1.51%** (within 2% trust gate) |
| Reconciliation residual attribution | **100% itemized** |

See [`docs/architecture/slice_1_completion_summary.md`](docs/architecture/slice_1_completion_summary.md)
for the engineering walkthrough.

---

## Tech Stack

| Layer | Tech |
|---|---|
| Frontend | Next.js 16 · TypeScript · Tailwind · ECharts |
| API | FastAPI · Pydantic · python-jose JWT |
| Metric definitions | YAML DSL (PyYAML) |
| Data warehouse | Databricks Lakehouse · Delta Lake · Kimball star schema |
| ETL | PySpark on Databricks classic compute |
| Orchestration | Databricks Workflows |
| Cache | Redis (Phase 5) |
| Streaming (Phase 4.5) | Auto Loader · Structured Streaming · Watermark · Exactly-once |
| Package management | uv (Python) · npm (Node) |
| Deployment | Vercel (frontend) · (TBD) backend |

---

## Repository Layout
analytics-platform/
├── frontend/                       # Next.js portal
├── metrics-service/                # FastAPI + YAML metric definitions
│   ├── app/                        # API service
│   └── data_quality/               # YAML-driven DQ framework
├── databricks-notebooks/slice_1/   # PySpark ETL (notebook 01-04)
├── docs/
│   ├── architecture/               # Design docs + completion summaries
│   ├── data_modeling/              # Star schema DDL
│   ├── reconciliation/             # Quantitative reconciliation methodology
│   ├── data_contracts/             # Upstream data contracts
│   ├── demo/                       # Stakeholder demo scripts
│   ├── existing_data_inventory.md  # PBI page → data source mapping
│   ├── legacy_panoply_etl.md       # Legacy reverse-engineering
│   └── streaming_module_plan.md    # Phase 4.5 design
├── NORTH_STAR.md                   # Project guiding principles
├── PROJECT_CONTEXT.md              # Architectural decisions log
├── ROADMAP.md                      # Phase plan
└── PROGRESS.md                     # Current status + quantitative baseline
---

## Key Engineering Practices

- **Vertical Slice delivery** — end-to-end per PBI page, not waterfall layer-by-layer
- **Data Contracts before ingestion** — schema, quality, and SLA defined upstream
- **Versioned Metrics governance** — every metric carries version, owner, changelog,
  with explicit `breaking: true` annotation for semantic changes
- **Kimball dimensional modeling** — 1 fact + 3 conformed dims, ISO 8601 only
- **Materialized business rules** — `is_sales_attributable` column encodes
  sales-exclusion rule once at the data layer, replacing scattered WHERE filters
- **Multi-tier DQ SLO** — PASS / WARN / FAIL calibrated to empirical 0.15% baseline,
  avoiding alert fatigue
- **DQ-as-Gate pattern** — FAIL threshold halts pipeline before write
- **DST-aware timezone** — `from_utc_timestamp('America/New_York')` corrects legacy
  `processed_at - 5h` summer drift
- **Line-level refund netting** — `refunded_quantity` covers all `restock_type`
  values (return / no_restock / cancel / legacy_restock)
- **Fault-tolerant ETL** — auto-detects upstream table availability, degrades
  gracefully when not yet synced
- **Quantitative reconciliation** — trust gate redefined as "overall < 2% AND
  fully itemized residual" instead of "95% buckets PASS", avoiding
  small-denominator distortion
- **Schema-evolution tolerance** — ERS dual-format auto-detection,
  historical CSVs replayable

---

## Architectural Decisions

22 decisions logged in [`PROJECT_CONTEXT.md`](PROJECT_CONTEXT.md). Highlights:

- **Decision 10** — Vertical Slice methodology
- **Decision 11** — ISO 8601 only (drop US-week compatibility)
- **Decision 17** — DST-aware timezone (corrects legacy `processed_at - 5h` bug)
- **Decision 18** — Multi-tier DQ SLO calibrated against empirical baseline
- **Decision 19** — ERS dual-schema ingest auto-detection
- **Decision 21** — `channel_group` as Kimball roll-up hierarchy
  (replaces "GA4 compat" framing)
- **Decision 22 v3** — Materialized `is_sales_attributable` + line-level refund netting

---

## Project Status

| Phase | Scope | Status |
|---|---|---|
| Phase 1 | Frontend portal MVP + Data Contracts | ✅ Done |
| Phase 2A | FastAPI metrics service + YAML metric layer | ✅ Done |
| Slice 1 | Style × Channel quantity (Phase 2B/3 vertical slice) | ✅ Done |
| Slice 2 | Revenue page | 🔜 Next |
| Slice 3 | Refunds page | 📋 Planned |
| Slice 4 | ROAS page | 📋 Planned |
| Phase 4 | Workflows orchestration + DQ gates | Designed ([doc](docs/architecture/phase4_orchestration_design.md)) |
| Phase 4.5 | Streaming (real-time anomaly monitoring) | Designed ([doc](docs/streaming_module_plan.md)) |
| Phase 5 | Redis cache + metrics catalog + lineage | 📋 Planned |
| Phase 6 | Deployment + documentation + cost analysis | 📋 Planned |

---

## Local Development

### Prerequisites
- Node.js 20+
- Python 3.11+
- [uv](https://github.com/astral-sh/uv) Python package manager
- Databricks workspace access (for notebooks)

### Run

```bash
# Terminal 1 — Frontend (port 3000)
cd frontend
npm install
npm run dev

# Terminal 2 — Metrics service (port 8000)
cd metrics-service
uv sync
uv run uvicorn app.main:app --reload --port 8000
```

Sign in at http://localhost:3000 with the demo account.

### Databricks notebooks
PySpark notebooks under `databricks-notebooks/slice_1/` run on Databricks
classic compute (DataFrame cache required). Personal Compute / 4-core is
sufficient. OAuth U2M is used for the metrics service ↔ SQL Warehouse
connection (no PAT).

---

## Documentation

- [`docs/architecture/slice_1_design.md`](docs/architecture/slice_1_design.md) — Slice 1 architecture design (19 sections)
- [`docs/architecture/slice_1_completion_summary.md`](docs/architecture/slice_1_completion_summary.md) — Slice 1 completion summary + resume headlines
- [`docs/architecture/phase4_orchestration_design.md`](docs/architecture/phase4_orchestration_design.md) — Phase 4 orchestration design
- [`docs/streaming_module_plan.md`](docs/streaming_module_plan.md) — Phase 4.5 streaming module plan
- [`docs/data_modeling/star_schema_ddl.sql`](docs/data_modeling/star_schema_ddl.sql) — Production-synced DDL (v2.0)
- [`docs/reconciliation/`](docs/reconciliation/) — Reconciliation methodology, SQL, Python tooling, reports
- [`docs/legacy_panoply_etl.md`](docs/legacy_panoply_etl.md) — Legacy Panoply pipeline reverse-engineering
- [`docs/existing_data_inventory.md`](docs/existing_data_inventory.md) — PBI page → data source mapping
- [`metrics-service/README.md`](metrics-service/README.md) — Metrics service detail
- [`metrics-service/data_quality/README.md`](metrics-service/data_quality/README.md) — Data quality framework detail

---

## Author

Sia Song — designing and building this as a single-engineer end-to-end
data platform project.