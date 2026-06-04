"""
Phase 5 — Data lineage endpoint
GET /lineage  ->  { categories, nodes, edges } : source -> ... -> dashboard

Curated lineage config (declared here for clarity; in a fuller build you'd
externalize it to lineage.yaml or parse it from the metric SQL). Adjust the
node names / edges to match your exact tables.

Drop-in: save as app/routers/lineage.py, then in main.py:
    from app.routers.lineage import router as lineage_router
    app.include_router(lineage_router)
"""
from fastapi import APIRouter

router = APIRouter(tags=["lineage"])

CATEGORIES = ["Source", "Raw / Silver", "Warehouse", "Metric", "Dashboard"]

# (id, display name, category index)
NODES = [
    # Source
    ("shopify", "Shopify", 0),
    ("triple_whale", "Triple Whale", 0),
    ("ers", "ERS CSV", 0),
    ("amazon", "Amazon SP-API", 0),
    ("rt_events", "Realtime events", 0),
    ("date_seed", "Calendar seed", 0),
    # Raw / Silver
    ("slv_shopify", "shopify_32degrees.*", 1),
    ("slv_tw", "attribution_order_click", 1),
    ("slv_metafield", "order_metafield", 1),
    ("rt_orders", "silver_realtime_orders", 1),
    ("rt_ads", "silver_realtime_ads", 1),
    ("rt_attr", "silver_realtime_attributed", 1),
    ("amz_raw", "amazon raw", 1),
    # Warehouse
    ("fact", "fact_orders_line", 2),
    ("dim_date", "dim_date", 2),
    ("dim_channel", "dim_channel", 2),
    ("dim_product", "dim_product", 2),
    ("gold_rt", "gold_realtime_channel_health", 2),
    ("amz_gold", "amazon gold", 2),
    # Metric
    ("m_revenue", "revenue", 3),
    ("m_aov", "aov", 3),
    ("m_roas", "roas", 3),
    ("m_ad_spend", "ad_spend", 3),
    ("m_channel_health", "channel_health (RT)", 3),
    # Dashboard
    ("dash_slice1", "Style x Channel x Week", 4),
    ("dash_rt", "Real-time Channel Health", 4),
]

# (source, target)
EDGES = [
    ("shopify", "slv_shopify"),
    ("shopify", "slv_metafield"),
    ("triple_whale", "slv_tw"),
    ("ers", "dim_product"),
    ("amazon", "amz_raw"),
    ("rt_events", "rt_orders"),
    ("rt_events", "rt_ads"),
    ("date_seed", "dim_date"),

    ("slv_shopify", "fact"),
    ("slv_tw", "fact"),
    ("slv_metafield", "fact"),
    ("slv_tw", "dim_channel"),
    ("amz_raw", "amz_gold"),

    ("dim_date", "fact"),
    ("dim_channel", "fact"),
    ("dim_product", "fact"),

    ("rt_orders", "rt_attr"),
    ("rt_ads", "rt_attr"),
    ("rt_attr", "gold_rt"),

    ("fact", "m_revenue"),
    ("fact", "m_aov"),
    ("fact", "m_roas"),
    ("fact", "m_ad_spend"),
    ("gold_rt", "m_channel_health"),

    ("m_revenue", "dash_slice1"),
    ("m_aov", "dash_slice1"),
    ("m_roas", "dash_slice1"),
    ("m_ad_spend", "dash_slice1"),
    ("m_channel_health", "dash_rt"),
]


@router.get("/lineage")
def lineage():
    nodes = [{"id": i, "name": n, "category": c} for (i, n, c) in NODES]
    edges = [{"source": s, "target": t} for (s, t) in EDGES]
    return {"categories": CATEGORIES, "nodes": nodes, "edges": edges}
