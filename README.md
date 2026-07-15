![CI](https://github.com/sichensong-99/analytics-platform/actions/workflows/ci.yml/badge.svg)

# Internal Analytics Platform

> End-to-end data platform replacing Power BI Service for a retailer's ecommerce
> team — ingests multi-source data into a Lakehouse, serves governed metrics
> through a versioned API, and surfaces them in a self-service web portal.
> Owned end to end: data contracts, dimensional modeling, PySpark ETL, streaming,
> metrics API, portal, orchestration, and production deployment on Azure.

![stack](https://img.shields.io/badge/stack-Databricks%20%7C%20FastAPI%20%7C%20Next.js%20%7C%20Azure-blue)
![scale](https://img.shields.io/badge/scale-44M%20order%20lines-informational)
![reconciliation](https://img.shields.io/badge/customer%20classification-zero%20residual-brightgreen)
![slice1](https://img.shields.io/badge/Slice%201%20reconciliation-%E2%88%921.51%25-brightgreen)

---

## Reconciliation as falsification

Migrating a report off a legacy warehouse has an obvious success criterion:
make the new numbers match the old ones. I think that criterion is wrong. It
assumes the legacy report was right, and it turns reconciliation into a search
for agreement rather than a test.

So for the customer classification rebuild (first-time vs returning buyer,
13,163,530 rows) I wrote down a falsifiable prediction **before** querying:
the legacy pipeline's order history is shallow, so it cannot see a customer's
earlier purchases and should therefore **over-count first-time buyers**.

The data said the opposite. First-time came in **72 rows low**, not high. My
hypothesis was wrong, in direction, and I did not rewrite it after the fact.
Chasing that inversion is what surfaced the real mechanism — and the rebuild
only became trustworthy once the explanation survived a test designed to break
it, rather than one designed to confirm it.

| Check | Result |
|---|---|
| Order sets, day by day | identical (7,965 / 9,014 / 10,853) |
| `Returning` totals | 14,544 = 14,544 |
| `First-time + Returning` | 13,288 = 13,288 |
| Residual | **116 rows, 100% itemized** — 18 history depth · 90 email-null first-time · 8 email-null returning |
| Fan-out on 13.16M rows | zero |
| Orders the legacy report silently dropped | **0.35% more recovered — 92% of them first-time buyers** |

Eight independent verification layers stood behind it: parity 10/10 · row-count
identity · Delta time travel · internal consistency · **method independence**
(`MIN` vs `ROW_NUMBER` implemented separately and compared) · day-by-day
cross-layer reconciliation (3,800+ days, zero delta) · hand calculation ·
left-censoring curve.

Methodology, SQL and tooling: [`docs/reconciliation/`](docs/reconciliation/)

---

## Architecture

```
Next.js portal (dashboards · metrics catalog · lineage UI)
        ↓ HTTP + JWT
FastAPI metrics service (Redis cache-aside · YAML metric layer · query binding)
        ↓ SQL
Databricks Lakehouse (Kimball star schema · Delta Lake · DST-aware)
        ↑ batch ETL + Auto Loader / Structured Streaming
Shopify · Triple Whale · Amazon SP-API · GA4 · ERS master · freight CSVs
        ↑ orchestrate
Databricks Workflows (DAG · multi-tier DQ gates · alerts)
        ↑ provision
Azure Container Apps · ACR · Key Vault · Terraform
```

---

## Results

| | |
|---|---|
| Shopify `order_line` (full table) | 44.67M |
| TW `attribution_order_click` (full table) | 25.26M |
| Order lines processed (Slice 1 ETL window) | 9.97M |
| Cross-source join match rate | 99.72% |
| Channel DQ unmatched | 0.318% (PASS) |
| Product DQ unmatched | 0.000% (PASS) |
| Slice 1 reconciliation vs legacy | −1.51% (within 2% trust gate), residual **100% itemized** |
| Customer classification reconciliation | **zero residual** on 13.16M rows |
| Metrics API, cold query (~10M-row fact) | 5,086 ms |
| Metrics API, warm (Redis cache hit) | **16.6 ms** |

The 16.6 ms figure is a per-repeated-request number within TTL, **not** an
average production saving — that depends on hit rate, which is not yet
instrumented. Full caveats: [`docs/benchmarks/redis_cache_benchmark.md`](docs/benchmarks/redis_cache_benchmark.md)

---

## Tech Stack

| Layer | Tech |
|---|---|
| Frontend | Next.js 16 · TypeScript · Tailwind · ECharts |
| API | FastAPI · Pydantic · python-jose JWT |
| Metric definitions | YAML DSL (PyYAML) |
| Data warehouse | Databricks Lakehouse · Delta Lake · Kimball star schema |
| ETL | PySpark on Databricks |
| Streaming | Auto Loader · Structured Streaming · watermark · exactly-once |
| Orchestration | Databricks Workflows (Airflow DAG equivalent included for comparison) |
| Cache | Redis (cache-aside) |
| Infrastructure | Azure Container Apps · ACR · Key Vault · Log Analytics · **Terraform** |
| Package management | uv (Python) · npm (Node) |

---

## Repository Layout

```
analytics-platform/
├── frontend/                       # Next.js portal
├── metrics-service/                # FastAPI + YAML metric definitions
│   ├── app/                        # API service (routers · cache · client)
│   └── data_quality/               # YAML-driven DQ framework
├── databricks-notebooks/slice_1/   # PySpark ETL (notebook 01-07 · DQ gate · lineage)
├── streaming/                      # Auto Loader ingest · stream-stream join · gold anomaly
├── databricks-workflows/           # Production job definitions (JSON)
├── airflow/dags/                   # Same DAG in Airflow, for the orchestration comparison
├── infra/                          # Terraform — Container Apps · ACR · Key Vault
├── scripts/                        # Seed generators + tooling
└── docs/
    ├── architecture/               # Design docs + completion summaries
    ├── data_modeling/              # Star schema DDL
    ├── reconciliation/             # Reconciliation methodology, SQL, tooling
    ├── data_contracts/             # Upstream data contracts
    ├── benchmarks/                 # Redis cache benchmark
    └── RUNBOOK.md                  # Operational runbook
```

---

## Key Engineering Practices

- **Reconciliation as falsification** — a migration is tested by trying to break
  the hypothesis, not by matching the legacy number (see above)
- **Vertical Slice delivery** — end-to-end per report page, not waterfall layer-by-layer
- **Data Contracts before ingestion** — schema, quality, and SLA defined upstream
- **Versioned Metrics governance** — every metric carries version, owner, changelog,
  with explicit `breaking: true` annotation for semantic changes
- **Every business metric is defined in `definitions.yaml`** — hand-written
  endpoints were retired so this holds without exception
- **Kimball dimensional modeling** — fact + conformed dims, ISO 8601 only, SCD2
  where history is actually needed (SCD1 elsewhere, deliberately)
- **Materialized business rules** — `is_sales_attributable` encodes the
  sales-exclusion rule once at the data layer, replacing scattered WHERE filters
- **Multi-tier DQ SLO** — PASS / WARN / FAIL calibrated to an empirical 0.15%
  baseline, avoiding alert fatigue
- **DQ-as-Gate** — FAIL threshold halts the pipeline before write
- **DST-aware timezone** — `from_utc_timestamp('America/New_York')` corrects a
  legacy `processed_at - 5h` summer drift
- **Line-level refund netting** — `refunded_quantity` covers every `restock_type`
- **Fault-tolerant ETL** — auto-detects upstream table availability, degrades
  gracefully when a source is not yet synced
- **Schema-evolution tolerance** — dual-format auto-detection, historical CSVs replayable
- **Deployment gate** — an eight-step release checklist written after two
  production incidents; explicit traffic weights and a shadow revision

---

## Architectural Decisions

Decisions are logged with trade-offs in an internal decision log. Ones that
shaped the platform most:

- **Vertical Slice methodology** — ship one report end-to-end before broadening
- **ISO 8601 only** — drop US-week compatibility rather than carry two calendars
- **DST-aware timezone** — corrects the legacy `processed_at - 5h` bug
- **Multi-tier DQ SLO** — calibrated against an empirical baseline, not a guess
- **`channel_group` as a Kimball roll-up hierarchy** — replaces "GA4 compat" framing
- **Materialized `is_sales_attributable`** + line-level refund netting
- **SCD1 first, SCD2 only when a real as-of requirement appeared** — deferring
  complexity, then consciously upgrading, is itself the decision
- **Databricks Workflows over Airflow** — with the conditions under which I would
  switch written down: [`docs/orchestration_workflows_vs_airflow.md`](docs/orchestration_workflows_vs_airflow.md)

---

## Project Status

| Area | Status |
|---|---|
| Frontend portal · Data Contracts | ✅ |
| FastAPI metrics service · YAML metric layer | ✅ |
| Slice 1 — Style × Channel quantity, end-to-end | ✅ reconciled |
| Customer classification (first-time / returning) | ✅ zero residual |
| Databricks Workflows orchestration · DQ gates | ✅ running daily |
| Streaming — Auto Loader · watermark · exactly-once | ✅ |
| Redis cache · metrics catalog · lineage UI | ✅ |
| Amazon FBA SP-API ingestion (self-built) | ✅ |
| Azure deployment · Terraform · runbook | ✅ |

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

The metrics service imports and runs without a warehouse configured
(`METRICS_DATA_SOURCE=mock`), which is what CI exercises.

### Databricks notebooks
PySpark notebooks under `databricks-notebooks/slice_1/` run on Databricks
classic compute. OAuth is used for the metrics service ↔ SQL Warehouse
connection (no PAT).

---

## Documentation

- [`docs/reconciliation/`](docs/reconciliation/) — reconciliation methodology, SQL, Python tooling
- [`docs/architecture/slice_1_design.md`](docs/architecture/slice_1_design.md) — Slice 1 architecture design (19 sections)
- [`docs/architecture/slice_1_completion_summary.md`](docs/architecture/slice_1_completion_summary.md) — Slice 1 completion summary
- [`docs/architecture/phase4_orchestration_design.md`](docs/architecture/phase4_orchestration_design.md) — orchestration design
- [`docs/architecture/amazon_ingestion_design.md`](docs/architecture/amazon_ingestion_design.md) — Amazon SP-API ingestion design
- [`docs/orchestration_workflows_vs_airflow.md`](docs/orchestration_workflows_vs_airflow.md) — Workflows vs Airflow, and when I would switch
- [`docs/benchmarks/redis_cache_benchmark.md`](docs/benchmarks/redis_cache_benchmark.md) — cache benchmark + honest caveats
- [`docs/data_modeling/star_schema_ddl.sql`](docs/data_modeling/star_schema_ddl.sql) — production-synced DDL (v2.0)
- [`docs/data_contracts/`](docs/data_contracts/) — upstream data contracts
- [`docs/legacy_panoply_etl.md`](docs/legacy_panoply_etl.md) — legacy pipeline reverse-engineering
- [`docs/existing_data_inventory.md`](docs/existing_data_inventory.md) — report page → data source mapping
- [`docs/RUNBOOK.md`](docs/RUNBOOK.md) — operational runbook
- [`metrics-service/README.md`](metrics-service/README.md) — metrics service detail
- [`metrics-service/data_quality/README.md`](metrics-service/data_quality/README.md) — DQ framework detail

---

## Author

Sia Song — architecture, dimensional modeling, PySpark ETL, Structured Streaming,
metrics API, frontend, orchestration, and Azure deployment.