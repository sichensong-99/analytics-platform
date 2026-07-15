"""
Phase 5 — Data lineage endpoint  (auto-derived + curated overlay)
GET /lineage  ->  { categories, nodes, edges, source }

Data layer (table -> table) is read from a snapshot of Unity Catalog's
system.access.table_lineage, materialized by the slice_1_daily workflow into
  analytics_catalog.analytics_platform.lineage_edges
so the headless service principal can read it WITHOUT a system-table grant.

The metric -> dashboard layer is invisible to UC system tables (they only track
tables/columns), so it's added here as a small curated overlay.

If the snapshot table is unreadable/empty (not built yet, or mock mode) we fall
back to a fully-curated static graph.
"""
import os
from fastapi import APIRouter

router = APIRouter(tags=["lineage"])

CATALOG = "analytics_catalog"
SCHEMA = "analytics_platform"
EDGES_TABLE = f"{CATALOG}.{SCHEMA}.lineage_edges"

HOST = os.environ.get("DATABRICKS_HOST", "example.cloud.databricks.com")
HTTP_PATH = os.environ.get("DATABRICKS_HTTP_PATH", "/sql/1.0/warehouses/placeholder")
DATA_SOURCE = os.environ.get("METRICS_DATA_SOURCE", "databricks")

CATEGORIES = ["Source", "Raw / Silver", "Warehouse", "Metric", "Dashboard"]

# curated overlay: (warehouse_table_short, metric_id, metric_label, dash_id, dash_label)
OVERLAY = [
    ("fact_orders_line", "m_quantity", "quantity_by_style_channel_week", "dash_slice1", "Style × Channel × Week"),
    ("amazon_gold_receiving_by_sku", "m_amazon", "amazon_fba_receiving_by_sku", "dash_amazon", "Amazon FBA Receiving"),
]


def _connect():
    from databricks import sql
    cid = os.environ.get("DATABRICKS_CLIENT_ID")
    sec = os.environ.get("DATABRICKS_CLIENT_SECRET")
    if cid and sec:                                   # M2M — headless container
        from databricks.sdk.core import Config, oauth_service_principal

        def cred():
            cfg = Config(host=f"https://{HOST}", client_id=cid, client_secret=sec)
            return oauth_service_principal(cfg)

        return sql.connect(server_hostname=HOST, http_path=HTTP_PATH, credentials_provider=cred)
    return sql.connect(server_hostname=HOST, http_path=HTTP_PATH, auth_type="databricks-oauth")


def _short(full_name: str) -> str:
    """analytics_catalog.shopify_raw.order -> shopify_raw.order"""
    parts = full_name.split(".")
    return ".".join(parts[1:]) if len(parts) >= 3 else full_name


def _classify(full_name: str) -> int:
    parts = full_name.split(".")
    schema = parts[1] if len(parts) >= 3 else ""
    table = parts[-1].lower()
    if table.startswith(("fact_", "dim_", "gold_", "amazon_gold_")):
        return 2                                      # Warehouse
    if table.startswith(("silver_", "amazon_silver_", "amazon_bronze_")):
        return 1                                      # Raw / Silver
    if schema != SCHEMA:
        return 0                                      # upstream Source
    return 1


def _auto_edges() -> list[tuple[str, str]]:
    if DATA_SOURCE == "mock":
        return []
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT source, target FROM {EDGES_TABLE}")
            rows = [(r[0], r[1]) for r in cur.fetchall()]
    finally:
        conn.close()
    return [(s, t) for (s, t) in rows if s and t and s != t]


# ---- fully-curated static fallback ----
_FB_NODES = [
    ("shopify", "Shopify", 0), ("triple_whale", "Triple Whale", 0), ("ers", "ERS CSV", 0),
    ("amazon", "Amazon SP-API", 0),
    ("slv_shopify", "shopify_raw.*", 1), ("slv_tw", "attribution_order_click", 1),
    ("amz_silver", "amazon_silver_*", 1),
    ("fact", "fact_orders_line", 2), ("dim_date", "dim_date", 2),
    ("dim_channel", "dim_channel", 2), ("dim_product", "dim_product", 2),
    ("amz_gold", "amazon_gold_receiving_by_sku", 2),
    ("m_quantity", "quantity_by_style_channel_week", 3), ("m_amazon", "amazon_fba_receiving_by_sku", 3),
    ("dash_slice1", "Style × Channel × Week", 4), ("dash_amazon", "Amazon FBA Receiving", 4),
]
_FB_EDGES = [
    ("shopify", "slv_shopify"), ("triple_whale", "slv_tw"), ("ers", "dim_product"), ("amazon", "amz_silver"),
    ("slv_shopify", "fact"), ("slv_tw", "fact"), ("slv_tw", "dim_channel"),
    ("dim_date", "fact"), ("dim_channel", "fact"), ("dim_product", "fact"), ("amz_silver", "amz_gold"),
    ("fact", "m_quantity"), ("amz_gold", "m_amazon"),
    ("m_quantity", "dash_slice1"), ("m_amazon", "dash_amazon"),
]


def _curated():
    return {
        "categories": CATEGORIES,
        "nodes": [{"id": i, "name": n, "category": c} for (i, n, c) in _FB_NODES],
        "edges": [{"source": s, "target": t} for (s, t) in _FB_EDGES],
        "source": "curated",
    }


@router.get("/lineage")
def lineage():
    try:
        auto = _auto_edges()
    except Exception:
        auto = []
    if not auto:
        return _curated()                              # snapshot unavailable -> static

    nodes: dict[str, dict] = {}

    def add(full_name: str) -> str:
        nid = _short(full_name)
        if nid not in nodes:
            nodes[nid] = {"id": nid, "name": nid, "category": _classify(full_name)}
        return nid

    edges: list[dict] = []
    for s, t in auto:
        edges.append({"source": add(s), "target": add(t)})

    # curated overlay: metric + dashboard layers
    for tbl, mid, mlabel, did, dlabel in OVERLAY:
        match = next((nid for nid in nodes if nid.split(".")[-1] == tbl), None)
        if not match:
            continue
        nodes[mid] = {"id": mid, "name": mlabel, "category": 3}
        nodes[did] = {"id": did, "name": dlabel, "category": 4}
        edges.append({"source": match, "target": mid})
        edges.append({"source": mid, "target": did})

    return {
        "categories": CATEGORIES,
        "nodes": list(nodes.values()),
        "edges": edges,
        "source": "unity_catalog_system_tables + curated_overlay",
    }
