"""
Metrics Service — Main FastAPI Application

Provides RESTful endpoints for querying business metrics.
"""

from datetime import date
from typing import Any, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from pydantic import BaseModel

from app.auth import UserPayload, get_current_user
from app.databricks_client import run_query
from app.metrics_loader import get_metric, list_metrics
from app.routers.realtime import router as realtime_router

from app.routers.catalog import router as catalog_router
from app.routers.lineage import router as lineage_router
from app.cache import cached_query, make_key


# ============ App init ============

app = FastAPI(
    title="Internal Metrics Service",
    description="Unified metrics API backed by YAML-driven metric layer.",
    version="0.2.0",
)

app.include_router(realtime_router)
app.include_router(catalog_router)
app.include_router(lineage_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============ OpenAPI Bearer auth ============

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    openapi_schema["components"]["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
        }
    }
    for path in openapi_schema["paths"].values():
        for operation in path.values():
            operation["security"] = [{"BearerAuth": []}]
    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi


# ============ Response models ============

class MetricSummary(BaseModel):
    id: str
    name: str
    description: str
    owner: str
    unit: str
    version: str
    status: str
    source_tables: list[str]


class MetricResponse(BaseModel):
    metric_id: str
    name: str
    version: str
    unit: str
    params: dict
    data: list[dict]


# ============ Helpers ============

def _serialize_params(params: dict[str, Any]) -> dict[str, Any]:
    """
    Serialize params for JSON response.
    - date -> ISO string
    - None -> dropped
    - list -> kept as list
    """
    out: dict[str, Any] = {}
    for k, v in params.items():
        if v is None:
            continue
        if isinstance(v, date):
            out[k] = v.isoformat()
        elif isinstance(v, list):
            out[k] = v
        else:
            out[k] = str(v)
    return out


# ============ Health check (no auth) ============

@app.get("/health")
def health_check():
    """Simple health check, used by ops / uptime monitors."""
    return {"status": "ok"}


# ============ Metrics endpoints ============

@app.get("/metrics", response_model=list[MetricSummary])
def list_all_metrics(user: UserPayload = Depends(get_current_user)):
    """Return summary info for all metrics — the metrics catalog."""
    return list_metrics()


@app.get("/metrics/{metric_id}", response_model=MetricResponse)
def query_metric(
    metric_id: str,
    start_date: date = Query(..., description="Start date (inclusive)"),
    end_date: date = Query(..., description="End date (inclusive)"),
    # === Generic optional dimensional filters ===
    # Repeat parameter to send multiple values, e.g.:
    #   ?channels=google-ads&channels=meta&seasons=F23
    channels: Optional[list[str]] = Query(
        None, description="Filter by channel_source (TW). Repeat to pass multiple."
    ),
    seasons: Optional[list[str]] = Query(
        None, description="Filter by ERS season. Repeat to pass multiple."
    ),
    styles: Optional[list[str]] = Query(
        None, description="Filter by ERS vend_id (style). Repeat to pass multiple."
    ),
    user: UserPayload = Depends(get_current_user),
):
    """
    Query a metric by ID over a date range, with optional dimensional filters.

    Backward-compatible: existing metrics that don't declare these filters
    receive them as no-ops (mock client ignores; real SQL guard via `:x IS NULL` pattern).
    """
    metric = get_metric(metric_id)
    if metric is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Metric '{metric_id}' not found",
        )

    if end_date < start_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="end_date must be >= start_date",
        )

    params: dict[str, Any] = {
        "start_date": start_date,
        "end_date": end_date,
        "channels": channels,
        "seasons": seasons,
        "styles": styles,
    }

    rows = cached_query(
    make_key(f"snapshot:{metric_id}", params),
    lambda: run_query(metric["sql"], params)
)

    return MetricResponse(
        metric_id=metric_id,
        name=metric["name"],
        version=metric["version"],
        unit=metric["unit"],
        params=_serialize_params(params),
        data=rows,
    )
# ============ Snapshot metrics (no date range) ============

class SnapshotResponse(BaseModel):
    metric_id: str
    name: str
    version: str
    unit: str
    params: dict
    data: list[dict]


@app.get("/snapshot/{metric_id}", response_model=SnapshotResponse)
def query_snapshot_metric(
    metric_id: str,
    # Generic optional filters for snapshot-style metrics
    statuses: Optional[list[str]] = Query(
        None, description="Filter by shipment_status. Repeat to pass multiple."
    ),
    fcs: Optional[list[str]] = Query(
        None, description="Filter by destination_fc_id. Repeat to pass multiple."
    ),
    user: UserPayload = Depends(get_current_user),
):
    """
    Query a snapshot-style metric (no date range) — e.g. current FBA receiving
    status. Distinct from /metrics/{id} which requires a date window.
    """
    metric = get_metric(metric_id)
    if metric is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Metric '{metric_id}' not found",
        )

    params: dict[str, Any] = {
        "statuses": statuses,
        "fcs": fcs,
    }

    rows = cached_query(
    make_key(metric_id, params),
    lambda: run_query(metric["sql"], params)
)

    return SnapshotResponse(
        metric_id=metric_id,
        name=metric["name"],
        version=metric["version"],
        unit=metric["unit"],
        params=_serialize_params(params),
        data=rows,
    )