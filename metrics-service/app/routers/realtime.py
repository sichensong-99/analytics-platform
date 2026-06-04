"""
Phase 4.5 — Step 5: real-time serving layer
GET /metrics/channel-health  ->  latest gold_realtime_channel_health windows

Self-contained on purpose: it connects to Databricks itself (M2M if the service
principal creds are present — same as the headless container — else local OAuth
U2M), and falls back to mock data so the frontend can be built without the
warehouse.

Drop-in: save as app/routers/realtime.py, then in main.py:
    from app.routers.realtime import router as realtime_router
    app.include_router(realtime_router)

Optional cleanup: if you'd rather reuse your existing metrics-service connection
helper / dual-mode switch, just replace _connect() and the mock branch with it.
"""
import os
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter

router = APIRouter(prefix="/metrics", tags=["realtime"])

CATALOG = "mvdevdatabricks"
SCHEMA  = "analytics_platform_32degrees"
GOLD    = f"{CATALOG}.{SCHEMA}.gold_realtime_channel_health"

HOST        = os.environ.get("DATABRICKS_HOST", "dbc-620cc0fc-b4ee.cloud.databricks.com")
HTTP_PATH   = os.environ.get("DATABRICKS_HTTP_PATH", "/sql/1.0/warehouses/39f94dd6ed9a78a4")
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

        return sql.connect(server_hostname=HOST, http_path=HTTP_PATH,
                           credentials_provider=cred)
    return sql.connect(server_hostname=HOST, http_path=HTTP_PATH,   # local U2M
                       auth_type="databricks-oauth")


def _mock(minutes: int):
    now = datetime.now(timezone.utc)
    channels = ["facebook", "google", "tiktok", "bing"]
    out = []
    for i in range(minutes):
        ws = now - timedelta(minutes=i)
        for ch in channels:
            crash = ch == "facebook" and i < 3        # last 3 min: facebook crashes
            roas = 0.4 if crash else round(24 + (hash((ch, i)) % 80) / 10, 2)
            spend = round(300 + (hash((ch, i)) % 200), 2)
            out.append({
                "channel": ch,
                "window_start": ws.isoformat(),
                "window_end": (ws + timedelta(minutes=5)).isoformat(),
                "total_spend": spend,
                "attributed_revenue": round(roas * spend, 2),
                "roas": roas,
                "order_count": 5 + (hash((ch, i)) % 40),
                "is_anomaly": crash,
                "last_updated": now.isoformat(),
            })
    return out


@router.get("/channel-health")
def channel_health(minutes: int = 30):
    """Latest per-channel ROAS windows. ?minutes= controls the lookback."""
    if DATA_SOURCE == "mock":
        return {"windows": _mock(minutes)}

    q = f"""
        SELECT channel, window_start, window_end,
               total_spend, attributed_revenue, roas,
               order_count, is_anomaly, last_updated
        FROM {GOLD}
        WHERE window_start >= current_timestamp() - INTERVAL {int(minutes)} MINUTES
        ORDER BY window_start DESC, channel
    """
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(q)
            cols = [c[0] for c in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    finally:
        conn.close()

    for r in rows:                                    # make timestamps JSON-safe
        for k in ("window_start", "window_end", "last_updated"):
            if r.get(k) is not None and not isinstance(r[k], str):
                r[k] = r[k].isoformat()
    return {"windows": rows}