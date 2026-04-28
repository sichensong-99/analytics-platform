# Internal Analytics Platform

End-to-end internal data platform replacing Power BI Service.
Built as a self-serve analytics solution with unified metrics governance.

---

## Architecture

```
Next.js (Frontend Portal)
        ↓ HTTP + JWT
FastAPI (Metrics Service + Cache)
        ↓ Load
Metric Layer (YAML DSL)
        ↓ SQL
Databricks Lakehouse (ODS / DWD / DWS + Dimensional Modeling)
        ↑ Orchestrate
Databricks Workflows + Data Quality Framework
```

---

## Repository Structure

| Folder | Purpose | Phase |
|---|---|---|
| `frontend/` | Next.js portal: dashboards, catalog, lineage UI | Phase 1 ✅ |
| `metrics-service/` | FastAPI metrics service + YAML metric layer | Phase 2A ✅ |
| `databricks-notebooks/` | Data warehouse modeling (PySpark) | Phase 2B / 3 |
| `docs/` | Project documentation | Ongoing |
| `docs/data_contracts/` | Data contracts for upstream sources | Phase 1 ✅ |

---

## Tech Stack

**Frontend**: Next.js · TypeScript · Tailwind CSS · ECharts
**Backend**: FastAPI · Pydantic · PyYAML · python-jose
**Data**: Databricks Lakehouse · Delta Lake · PySpark
**Orchestration**: Databricks Workflows
**Auth**: JWT (shared secret across services)

---

## Key Engineering Practices

- **Data Contracts** — Schema, quality, and SLA defined before ingestion
- **Versioned Metrics** — Each metric has version, owner, changelog
- **Layered Data Warehouse** — Medallion architecture (ODS / DWD / DWS)
- **Dimensional Modeling** — Kimball-style fact + dimension tables
- **Service Decoupling** — Frontend never queries the warehouse directly
- **Cost Awareness** — Caching, query optimization, ROI tracking

---

## Project Status

| Phase | Scope | Status |
|---|---|---|
| 1 | Next.js portal + Data Contracts + mock data | ✅ Done |
| 2A | FastAPI metrics service + YAML metric layer | ✅ Done |
| 2B / 3 | Databricks ODS / DWD / DWS modeling | ⏳ In progress |
| 4 | Workflows orchestration + data quality framework | 📋 Planned |
| 5 | Redis caching + Metrics Catalog + lineage | 📋 Planned |
| 6 | Production deployment + cost analysis | 📋 Planned |

---

## Local Development

### Prerequisites

- Node.js 20+
- Python 3.11+
- uv (Python package manager)

### Run

```bash
# Terminal 1 — Frontend (Next.js, port 3000)
cd frontend
npm install
npm run dev

# Terminal 2 — Metrics Service (FastAPI, port 8000)
cd metrics-service
uv sync
uv run uvicorn app.main:app --reload --port 8000
```

Open http://localhost:3000 and sign in with the demo accounts.

---

## Documentation

- [Phase 1 Summary](docs/phase1_summary.md)
- [Data Contract: Shopify Orders](docs/data_contracts/shopify_orders.md)
- [Data Contract: Triple Whale Attribution](docs/data_contracts/triplewhale_attribution.md)
- [Metrics Service README](metrics-service/README.md)

---

## Author

Built as an end-to-end demonstration of modern data platform engineering:
data contracts, metric governance, dimensional modeling, service decoupling,
and cost-conscious design.