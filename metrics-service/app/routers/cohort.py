"""
Slice 3b — Cohort serving layer
GET /cohort -> { monthly: [...], retention: [...] }

Serves the two pre-aggregated Delta tables built by the slice_1_daily
`cohort_build` task (window-function new/returning + retention matrix). Heavy
modeling lives in the pipeline; this endpoint just reads the results. Mock
fallback so the frontend can run without the warehouse.
"""
import os
from fastapi import APIRouter

router = APIRouter(tags=["cohort"])

CATALOG = "mvdevdatabricks"
SCHEMA = "analytics_platform_32degrees"
T_MONTHLY = f"{CATALOG}.{SCHEMA}.cohort_orders_monthly"
T_RETENTION = f"{CATALOG}.{SCHEMA}.cohort_retention"

HOST = os.environ.get("DATABRICKS_HOST", "dbc-620cc0fc-b4ee.cloud.databricks.com")
HTTP_PATH = os.environ.get("DATABRICKS_HTTP_PATH", "/sql/1.0/warehouses/39f94dd6ed9a78a4")
DATA_SOURCE = os.environ.get("METRICS_DATA_SOURCE", "databricks")


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


def _rows(cur, q):
    cur.execute(q)
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def _mock():
    import random
    months = [f"2025-{m:02d}" for m in range(1, 13)]
    monthly = []
    for i, m in enumerate(months):
        new = 800 + i * 30 + random.randint(0, 80)
        ret = 200 + i * 70 + random.randint(0, 80)
        monthly.append({"month": m, "new_orders": new, "returning_orders": ret,
                        "new_revenue": round(new * 95.0, 2), "returning_revenue": round(ret * 110.0, 2)})
    retention = []
    for ci, m in enumerate(months):
        size = 1000 - ci * 20
        for p in range(0, 12 - ci):
            rate = 1.0 if p == 0 else round(max(0.0, 1.0 - p * 0.12 + random.uniform(-0.02, 0.02)), 4)
            retention.append({"cohort_month": m, "period_index": p,
                              "active_customers": int(size * rate), "cohort_size": size, "retention_rate": rate})
    return {"monthly": monthly, "retention": retention}


@router.get("/cohort")
def cohort():
    if DATA_SOURCE == "mock":
        return _mock()
    conn = _connect()
    try:
        with conn.cursor() as cur:
            monthly = _rows(cur, f"""
                SELECT date_format(order_month, 'yyyy-MM') AS month,
                       new_orders, returning_orders, new_revenue, returning_revenue
                FROM {T_MONTHLY} ORDER BY order_month
            """)
            retention = _rows(cur, f"""
                SELECT date_format(cohort_month, 'yyyy-MM') AS cohort_month,
                       period_index, active_customers, cohort_size, retention_rate
                FROM {T_RETENTION} ORDER BY cohort_month, period_index
            """)
    finally:
        conn.close()
    return {"monthly": monthly, "retention": retention}