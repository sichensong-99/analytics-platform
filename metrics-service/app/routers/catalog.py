"""
Phase 5 — Metrics Catalog endpoint
GET /catalog  ->  every metric from definitions.yaml + its metadata

Self-contained: it finds and parses definitions.yaml generically, so it works
regardless of your exact YAML field names (it tries common aliases). If your
service already has a YAML loader, you can swap _load_metrics() for it.

Drop-in: save as app/routers/catalog.py, then in main.py:
    from app.routers.catalog import router as catalog_router
    app.include_router(catalog_router)

If the file isn't auto-found, set:
    DEFINITIONS_PATH=/abs/path/to/definitions.yaml
"""
import os
from pathlib import Path
from fastapi import APIRouter

router = APIRouter(tags=["catalog"])

# where to look for the metric definitions file
_CANDIDATES = [
    os.environ.get("DEFINITIONS_PATH"),
    "definitions.yaml",
    "app/definitions.yaml",
    "metrics/definitions.yaml",
    "app/metrics/definitions.yaml",
]


def _first(d, *keys, default=None):
    for k in keys:
        if isinstance(d, dict) and d.get(k) not in (None, ""):
            return d[k]
    return default


def _normalize(key, body):
    body = body if isinstance(body, dict) else {}
    return {
        "key": key,
        "label": _first(body, "label", "name", "title", default=key),
        "description": _first(body, "description", "desc", "summary", default=""),
        "version": _first(body, "version", "ver"),
        "grain": _first(body, "grain", "granularity"),
        "definition": _first(body, "sql", "expression", "formula", "expr"),
        "unit": _first(body, "unit", "format"),
        "owner": _first(body, "owner", "team"),
        "changelog": _first(body, "changelog", "changes", "history", default=[]),
        "raw": body,
    }


def _load_metrics():
    import yaml
    path = next((p for p in _CANDIDATES if p and Path(p).exists()), None)
    if not path:
        return None  # not found -> caller falls back to mock
    doc = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    coll = doc.get("metrics", doc)  # supports {metrics: {...}} or a bare map / list
    out = []
    if isinstance(coll, dict):
        for k, body in coll.items():
            out.append(_normalize(k, body))
    elif isinstance(coll, list):
        for item in coll:
            k = _first(item or {}, "key", "name", "id", default="metric")
            out.append(_normalize(k, item))
    return out


def _mock():
    return [
        {"key": "revenue", "label": "Revenue", "description": "Net revenue after refunds",
         "version": 2, "grain": "order_line", "definition": "SUM(net_amount)", "unit": "USD",
         "owner": "analytics",
         "changelog": [{"version": 1, "note": "initial"},
                       {"version": 2, "note": "gross -> net (breaking)", "breaking": True}],
         "raw": {}},
        {"key": "aov", "label": "AOV", "description": "Average order value", "version": 1,
         "grain": "order", "definition": "revenue / order_count", "unit": "USD",
         "owner": "analytics", "changelog": [], "raw": {}},
        {"key": "roas", "label": "ROAS", "description": "Return on ad spend", "version": 1,
         "grain": "channel", "definition": "attributed_revenue / ad_spend", "unit": "x",
         "owner": "growth", "changelog": [], "raw": {}},
        {"key": "ad_spend", "label": "Ad Spend", "description": "Total ad spend", "version": 1,
         "grain": "channel", "definition": "SUM(ad_spend)", "unit": "USD",
         "owner": "growth", "changelog": [], "raw": {}},
    ]


@router.get("/catalog")
def catalog():
    metrics = _load_metrics()
    source = "definitions.yaml"
    if metrics is None:
        metrics, source = _mock(), "mock"
    return {"source": source, "count": len(metrics), "metrics": metrics}
