"""
Metrics Service — Main FastAPI Application

Provides RESTful endpoints for querying business metrics.
"""

from datetime import date
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from pydantic import BaseModel

from app.auth import UserPayload, get_current_user
from app.databricks_client import run_query
from app.metrics_loader import get_metric, list_metrics


# ============ App init ============

app = FastAPI(
    title="Internal Metrics Service",
    description="Unified metrics API backed by YAML-driven metric layer.",
    version="0.1.0",
)


# Allow Next.js frontend (running on localhost:3000) to call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============ OpenAPI Bearer auth (makes "Authorize" button appear) ============

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


# ============ Health check (no auth) ============

@app.get("/health")
def health_check():
    """Simple health check, used by ops / uptime monitors."""
    return {"status": "ok"}


# ============ Metrics endpoints ============

@app.get("/metrics", response_model=list[MetricSummary])
def list_all_metrics(user: UserPayload = Depends(get_current_user)):
    """
    Return summary info for all metrics — the metrics catalog.
    """
    return list_metrics()


@app.get("/metrics/{metric_id}", response_model=MetricResponse)
def query_metric(
    metric_id: str,
    start_date: date = Query(..., description="Start date (inclusive)"),
    end_date: date = Query(..., description="End date (inclusive)"),
    user: UserPayload = Depends(get_current_user),
):
    """
    Query a metric by ID over a date range.

    The SQL template is rendered with the given params, then executed
    against the data warehouse (currently mocked).
    """
    metric = get_metric(metric_id)
    if metric is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Metric '{metric_id}' not found",
        )

    # Validate date range
    if end_date < start_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="end_date must be >= start_date",
        )

    params = {
        "start_date": start_date,
        "end_date": end_date,
    }

    # Run the query (mock in Phase 2A)
    rows = run_query(metric["sql"], params)

    return MetricResponse(
        metric_id=metric_id,
        name=metric["name"],
        version=metric["version"],
        unit=metric["unit"],
        params={k: v.isoformat() for k, v in params.items()},
        data=rows,
    )