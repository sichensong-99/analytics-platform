# Internal Analytics Platform

End-to-end internal data platform replacing Power BI Service.

## Architecture

Frontend (Next.js) → Metrics Service (FastAPI) → Metric Layer (YAML) → Databricks Lakehouse

## Repository Structure

- `frontend/` — Next.js portal (Phase 1 ✅)
- `metrics-service/` — FastAPI metrics service (Phase 2)
- `databricks-notebooks/` — Data warehouse modeling (Phase 3)
- `docs/` — Documentation
  - `data_contracts/` — Data contracts for upstream sources

## Status

Phase 1: Portal MVP with mock data — In progress