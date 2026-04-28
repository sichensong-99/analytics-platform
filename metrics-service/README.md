# Metrics Service

Unified metrics API for the Internal Analytics Platform.
Backed by a YAML-driven metric layer, served via FastAPI.

---

## Architecture

```
Next.js Frontend
      ↓ HTTP + JWT
FastAPI Metrics Service  ← THIS REPO
      ↓ SQL
Metric Layer (YAML DSL)
      ↓
Databricks Lakehouse (Phase 3)
```

---

## Stack

- **FastAPI** — Web framework
- **Pydantic** — Request/response validation
- **PyYAML** — Metric definition loading
- **python-jose** — JWT verification (shared secret with Next.js)
- **uv** — Dependency management

---

## Endpoints

| Method | Path | Description | Auth Required |
|---|---|---|---|
| GET | `/health` | Health check | No |
| GET | `/metrics` | List all metrics (catalog) | Yes |
| GET | `/metrics/{metric_id}` | Query a metric over date range | Yes |

Interactive API docs: http://localhost:8000/docs

---

## Metric Definitions

Metrics are defined declaratively in `metrics/definitions.yaml`.

Each metric includes:
- **Version** — semantic versioning (v1.0, v1.1, ...)
- **Status** — active / deprecated / experimental
- **Owner** — team accountable for the definition
- **Business definition** — exact computation rules
- **Source tables** — upstream tables (used for lineage)
- **SQL template** — parameterized query
- **Changelog** — full history of definition changes

Adding a new metric requires only updating the YAML — no code changes.

---

## Project Structure

```
metrics-service/
├── app/                       # Application code
│   ├── __init__.py
│   ├── main.py                # FastAPI app + endpoints
│   ├── auth.py                # JWT verification
│   ├── metrics_loader.py      # YAML loader + caching
│   └── databricks_client.py   # Data warehouse client (mocked in Phase 2A)
├── metrics/
│   └── definitions.yaml       # Metric definitions (the metric layer)
├── tests/                     # Pytest test suite
├── pyproject.toml             # Project + dependencies
├── uv.lock                    # Locked dependency versions
└── .env                       # Local secrets (gitignored)
```

---

## Local Development

### Setup

```bash
# Install dependencies
uv sync

# Create .env file
echo "JWT_SECRET=dev-secret-change-in-production" > .env
echo "ENVIRONMENT=development" >> .env
```

### Run

```bash
uv run uvicorn app.main:app --reload --port 8000
```

### Add a dependency

```bash
uv add <package-name>            # Runtime dependency
uv add --dev <package-name>      # Dev-only dependency
```

### Run tests

```bash
uv run pytest
```

---

## Authentication

This service expects a JWT in the `Authorization: Bearer <token>` header.

The JWT is signed by the Next.js frontend using a **shared secret**
(`JWT_SECRET` environment variable). Both services must use the same
secret for tokens to be valid across them.

Default dev secret: `dev-secret-change-in-production`
(must be changed for production deployment)

---

## Phase 2A Status

- [x] FastAPI skeleton with auto-generated OpenAPI docs
- [x] YAML-driven metric definitions with versioning + changelog
- [x] JWT auth shared with Next.js frontend
- [x] Abstracted Databricks client (mock in 2A, real in Phase 3)
- [x] CORS configured for local frontend
- [x] Frontend integrated end-to-end

---

## Future Phases

| Phase | Scope |
|---|---|
| **2B / 3** | Replace mock Databricks client with real `databricks-sql-connector`; build ODS/DWD/DWS layers; Kimball dimensional modeling |
| **4** | Databricks Workflows orchestration; YAML-driven data quality framework |
| **5** | Redis caching layer; Metrics Catalog UI; metric lineage API |
| **6** | Production deployment; cost analysis report; documentation |