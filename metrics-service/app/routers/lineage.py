"""
Phase 5 — Data lineage endpoint (Unity Catalog system-tables driven)

GET /lineage -> { source, categories, nodes, edges }
               source -> silver -> warehouse -> metric -> dashboard

Data-layer lineage (raw -> silver -> fact/dim/gold) is derived LIVE from
Unity Catalog's system lineage table (system.access.table_lineage), which
auto-captures lineage from actual query/pipeline execution — not hand-drawn.

The metric -> dashboard layer is NOT a Unity Catalog concept (those are
app-level objects), so it's overlaid from a small curated map to extend
lineage end-to-end to the dashboards.

Resilience: if the system table is unreadable (e.g. the deployed service
principal lacks SELECT on system.access, or there's no recent lineage) the
endpoint falls back to a curated static graph so the UI never breaks.
"""
from fastapi import APIRouter

from app.databricks_client import run_query

router = APIRouter(tags=["lineage"])

PROJECT_SCHEMA = "analytics_platform_32degrees"
LINEAGE_LOOKBACK_DAYS = 90

CATEGORIES = ["Source", "Raw / Silver", "Warehouse", "Metric", "Dashboard"]

# ---- App-layer overlay (UC has no concept of metrics/dashboards) ----
# warehouse table name -> [metric id, ...]
TABLE_TO_METRICS = {
    "fact_orders_line": ["m_revenue", "m_aov", "m_roas", "m_ad_spend"],
    "gold_realtime_channel_health": ["m_channel_health"],
}
METRIC_NODES = [
    ("m_revenue", "revenue", 3),
    ("m_aov", "aov", 3),
    ("m_roas", "roas", 3),
    ("m_ad_spend", "ad_spend", 3),
    ("m_channel_health", "channel_health (RT)", 3),
]
METRIC_TO_DASH = {
    "m_revenue": ["dash_slice1"],
    "m_aov": ["dash_slice1"],
    "m_roas": ["dash_slice1"],
    "m_ad_spend": ["dash_slice1"],
    "m_channel_health": ["dash_rt"],
}
DASH_NODES = [
    ("dash_slice1", "Style x Channel x Week", 4),
    ("dash_rt", "Real-time Channel Health", 4),
]

# tables we never want to show in the business lineage graph
_INFRA_SUBSTRINGS = (
    "event_log", "_permission_test", "pipeline_watermark",
    "pipeline_run_history", "__unitystorage",
)


def _categorize(full_name: str) -> int:
    name = full_name.rsplit(".", 1)[-1].lower()
    if (name.startswith("fact_") or name.startswith("dim_")
            or name.startswith("gold_") or "_gold_" in name or name.endswith("_gold")):
        return 2  # Warehouse
    if "silver" in name or "bronze" in name:
        return 1  # Raw / Silver
    return 0      # Source (raw shopify / triple_whale / dpsync / federated)


def _short(full_name: str) -> str:
    parts = full_name.split(".")
    if PROJECT_SCHEMA in full_name:
        return parts[-1]                       # bare table for our schema
    return ".".join(parts[-2:]) if len(parts) >= 2 else full_name  # schema.table for sources


def _is_infra(full_name: str) -> bool:
    low = full_name.lower()
    return any(s in low for s in _INFRA_SUBSTRINGS)


def _load_system_lineage():
    """Query UC system lineage; return (nodes, edges) for the data layer, or None."""
    sql = f"""
        SELECT DISTINCT source_table_full_name AS src,
                        target_table_full_name AS tgt
        FROM system.access.table_lineage
        WHERE event_date >= current_date() - INTERVAL {LINEAGE_LOOKBACK_DAYS} DAYS
          AND source_table_full_name IS NOT NULL
          AND target_table_full_name IS NOT NULL
          AND source_table_full_name <> target_table_full_name
          AND (target_table_full_name LIKE '%{PROJECT_SCHEMA}%'
               OR source_table_full_name LIKE '%{PROJECT_SCHEMA}%')
    """
    rows = run_query(sql, {})
    if not rows:
        return None

    edges = []
    node_ids = {}
    for r in rows:
        src, tgt = r["src"], r["tgt"]
        if _is_infra(src) or _is_infra(tgt):
            continue
        for fn in (src, tgt):
            if fn not in node_ids:
                node_ids[fn] = {"id": fn, "name": _short(fn), "category": _categorize(fn)}
        edges.append({"source": src, "target": tgt})

    if not edges:
        return None
    return list(node_ids.values()), edges


def _overlay_app_layer(nodes, edges):
    """Append metric + dashboard nodes/edges on top of the data-layer graph."""
    present = {n["id"] for n in nodes}

    for full_name in list(present):
        table = full_name.rsplit(".", 1)[-1]
        for metric_id in TABLE_TO_METRICS.get(table, []):
            edges.append({"source": full_name, "target": metric_id})

    used_metrics = {e["target"] for e in edges if str(e["target"]).startswith("m_")}
    for mid, name, cat in METRIC_NODES:
        if mid in used_metrics:
            nodes.append({"id": mid, "name": name, "category": cat})

    used_dash = set()
    for mid in list(used_metrics):
        for dash_id in METRIC_TO_DASH.get(mid, []):
            edges.append({"source": mid, "target": dash_id})
            used_dash.add(dash_id)
    for did, name, cat in DASH_NODES:
        if did in used_dash:
            nodes.append({"id": did, "name": name, "category": cat})

    return nodes, edges


def _fallback():
    """Curated graph used only if system tables are unreadable/empty."""
    nodes = [
        {"id": "shopify", "name": "shopify_32degrees.*", "category": 0},
        {"id": "tw", "name": "triple_whale.attribution_order_click", "category": 0},
        {"id": "metafield", "name": "dpsync.order_metafield", "category": 0},
        {"id": "ers", "name": "ERS CSV", "category": 0},
        {"id": "fact_orders_line", "name": "fact_orders_line", "category": 2},
        {"id": "dim_date", "name": "dim_date", "category": 2},
        {"id": "dim_channel", "name": "dim_channel", "category": 2},
        {"id": "dim_product", "name": "dim_product", "category": 2},
    ]
    edges = [
        {"source": "shopify", "target": "fact_orders_line"},
        {"source": "tw", "target": "fact_orders_line"},
        {"source": "metafield", "target": "fact_orders_line"},
        {"source": "ers", "target": "dim_product"},
        {"source": "dim_date", "target": "fact_orders_line"},
        {"source": "dim_channel", "target": "fact_orders_line"},
        {"source": "dim_product", "target": "fact_orders_line"},
    ]
    return _overlay_app_layer(nodes, edges)


@router.get("/lineage")
def lineage():
    source = "unity_catalog_system_tables"
    try:
        result = _load_system_lineage()
    except Exception:
        result = None

    if result is None:
        nodes, edges = _fallback()
        source = "curated_fallback"
    else:
        nodes, edges = result
        nodes, edges = _overlay_app_layer(nodes, edges)

    return {"source": source, "categories": CATEGORIES, "nodes": nodes, "edges": edges}