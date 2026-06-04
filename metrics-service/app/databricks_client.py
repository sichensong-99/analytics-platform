"""
Databricks Client

Phase 2A: mock-only.
Day 4 (Slice 1): real Databricks SQL Warehouse connection added.
2026-05-28: snapshot metrics (statuses/fcs filters) + Amazon mock added.
2026-06-02: OAuth M2M (service principal) auth added for the headless
            container deploy (Phase 6.5).

Mode is controlled by METRICS_DATA_SOURCE env var:
  - "databricks": query the real SQL Warehouse (default)
  - "mock":       return mock data (offline dev / demo fallback)

Auth is controlled by DATABRICKS_AUTH_TYPE env var:
  - "oauth":     browser-based user login / U2M (local dev; default).
                 Cannot run headless — there is no browser in a container.
  - "oauth-m2m": service-principal client-credentials / M2M (headless cloud).
                 Reads DATABRICKS_CLIENT_ID + DATABRICKS_CLIENT_SECRET.
  - "pat":       personal access token via DATABRICKS_TOKEN.
"""

import os
import random
from datetime import date, timedelta
from typing import Any

from dotenv import load_dotenv

load_dotenv()

DATA_SOURCE = os.getenv("METRICS_DATA_SOURCE", "databricks").lower()

_DATABRICKS_CONNECTION: Any | None = None


# ============ Public interface ============

def run_query(sql: str, params: dict[str, Any]) -> list[dict]:
    """Run a SQL query and return rows as a list of dicts."""
    if DATA_SOURCE == "mock":
        return _run_query_mock(sql, params)

    try:
        return _run_query_databricks(sql, params)
    except Exception as e:
        raise RuntimeError(f"Databricks query failed: {e}") from e


# ============ Real Databricks connection ============

def _build_connect_kwargs() -> dict[str, Any]:
    hostname = os.environ["DATABRICKS_SERVER_HOSTNAME"]
    http_path = os.environ["DATABRICKS_HTTP_PATH"]
    auth_type = os.getenv("DATABRICKS_AUTH_TYPE", "oauth").lower()

    connect_kwargs: dict[str, Any] = {
        "server_hostname": hostname,
        "http_path": http_path,
    }

    if auth_type == "pat":
        # Personal access token (disabled by our org; kept for completeness).
        connect_kwargs["access_token"] = os.environ["DATABRICKS_TOKEN"]

    elif auth_type in ("oauth-m2m", "m2m"):
        # OAuth machine-to-machine: service-principal client-credentials.
        # The only flow that works headless in a container (U2M needs a
        # browser; PAT is disabled org-wide). Used by the cloud deploy (6.5).
        # Requires databricks-sdk (already a dependency of the SQL connector).
        from databricks.sdk.core import Config, oauth_service_principal

        client_id = os.environ["DATABRICKS_CLIENT_ID"]
        client_secret = os.environ["DATABRICKS_CLIENT_SECRET"]

        def _sp_credential_provider():
            config = Config(
                host=f"https://{hostname}",
                client_id=client_id,
                client_secret=client_secret,
            )
            return oauth_service_principal(config)

        connect_kwargs["credentials_provider"] = _sp_credential_provider

    else:
        # OAuth user-to-machine: browser-based login (local dev only).
        connect_kwargs["auth_type"] = "databricks-oauth"

    return connect_kwargs


def _get_databricks_connection():
    global _DATABRICKS_CONNECTION

    if _DATABRICKS_CONNECTION is not None:
        return _DATABRICKS_CONNECTION

    from databricks import sql as dbsql

    _DATABRICKS_CONNECTION = dbsql.connect(**_build_connect_kwargs())
    return _DATABRICKS_CONNECTION


def _reset_databricks_connection() -> None:
    global _DATABRICKS_CONNECTION

    if _DATABRICKS_CONNECTION is not None:
        try:
            _DATABRICKS_CONNECTION.close()
        except Exception:
            pass

    _DATABRICKS_CONNECTION = None


def _run_query_databricks(sql: str, params: dict[str, Any]) -> list[dict]:
    bound_sql, bound_params = _bind_params(sql, params)

    try:
        connection = _get_databricks_connection()

        with connection.cursor() as cursor:
            cursor.execute(bound_sql, bound_params)
            columns = [c[0] for c in cursor.description]
            rows = cursor.fetchall()

        return [dict(zip(columns, row)) for row in rows]

    except Exception:
        _reset_databricks_connection()
        raise


def _bind_params(sql: str, params: dict[str, Any]) -> tuple[str, dict]:
    """
    Resolve named markers into safe inline SQL before execution.
      * date params  -> integer yyyyMMdd literal (dim_date.date_key is BIGINT)
      * list filters -> (:x IS NULL OR col IN (:x)) guard resolved inline:
          - None/empty -> guard collapses to TRUE
          - list       -> quoted IN (...) literal
    """
    DATE_KEY_PARAMS = {"start_date", "end_date"}

    # Optional list filters using the (:x IS NULL OR col IN (:x)) guard.
    # Slice 1: channels/seasons/styles. Amazon snapshot: statuses/fcs.
    LIST_GUARD_PARAMS = {"channels", "seasons", "styles", "statuses", "fcs"}

    out_sql = sql

    # --- 1. Date params -> integer yyyyMMdd literal ---
    for key in DATE_KEY_PARAMS:
        if key not in params:
            continue
        value = params[key]
        if value is None:
            continue
        d = value if isinstance(value, date) else date.fromisoformat(str(value))
        date_key_int = int(d.strftime("%Y%m%d"))
        out_sql = out_sql.replace(f":{key}", str(date_key_int))

    # --- 2. Optional list filters -> resolve the guard inline ---
    for key in LIST_GUARD_PARAMS:
        marker = f":{key}"
        value = params.get(key)

        if not value:
            out_sql = out_sql.replace(marker, "NULL")
        else:
            safe_items = [str(v).replace("'", "''") for v in value]
            in_list = ", ".join(f"'{item}'" for item in safe_items)
            out_sql = out_sql.replace(f"{marker} IS NULL", "FALSE", 1)
            out_sql = out_sql.replace(marker, in_list)

    return out_sql, {}


# ============ Mock dispatch (offline / demo fallback) ============

def _run_query_mock(sql: str, params: dict[str, Any]) -> list[dict]:
    """Detect which metric is queried by SQL keywords, return fake data."""
    sql_lower = sql.lower()

    if "amazon_gold_receiving_by_sku" in sql_lower:
        return _mock_amazon_receiving(params)
    elif "fact_orders_line" in sql_lower:
        return _mock_quantity_by_style_channel_week(params)
    elif "daily_revenue" in sql_lower and "order_count" in sql_lower:
        return _mock_aov_by_day(params)
    elif "daily_revenue" in sql_lower:
        return _mock_revenue_by_day(params)
    elif (
        "channel_performance" in sql_lower
        and "ad_spend" in sql_lower
        and "group by event_date" in sql_lower
    ):
        return _mock_ad_spend_by_day(params)
    elif "channel_performance" in sql_lower:
        return _mock_roas_by_channel(params)
    else:
        return []


# ============ Mock data generators ============

def _date_range(params: dict) -> list[date]:
    start = _parse_date(params.get("start_date"))
    end = _parse_date(params.get("end_date"))
    if not start or not end or end < start:
        return []
    days = (end - start).days + 1
    return [start + timedelta(days=i) for i in range(days)]


def _parse_date(value) -> date | None:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    return None


def _mock_revenue_by_day(params: dict) -> list[dict]:
    return [
        {"date": d.isoformat(), "value": round(random.uniform(3000, 8000), 2)}
        for d in _date_range(params)
    ]


def _mock_aov_by_day(params: dict) -> list[dict]:
    return [
        {"date": d.isoformat(), "value": round(random.uniform(80, 180), 2)}
        for d in _date_range(params)
    ]


def _mock_roas_by_channel(params: dict) -> list[dict]:
    channels = ["Facebook", "Google", "TikTok", "Email", "Organic"]
    return [
        {"channel": ch, "value": round(random.uniform(2.5, 5.5), 2)}
        for ch in channels
    ]


def _mock_ad_spend_by_day(params: dict) -> list[dict]:
    rows = []
    for d in _date_range(params):
        for channel in ["Facebook", "Google", "TikTok"]:
            rows.append({
                "date": d.isoformat(),
                "channel": channel,
                "value": round(random.uniform(50, 300), 2),
            })
    return rows


def _mock_quantity_by_style_channel_week(params: dict) -> list[dict]:
    """Mock data for Slice 1 quantity_by_style_channel_week."""
    style_catalog = [
        ("PACKBAG", "Packable Backpack", "F23"),
        ("SILVERTOTE", "Silver Tote", "F23"),
        ("T3FK1451PRT", "Printed Fleece Pullover", "F22"),
        ("HEATER100", "Heated Vest", "F23"),
        ("WAFFLEHOOD", "Waffle Knit Hoodie", "F22"),
        ("STORMBOOT", "Storm Boot", "F23"),
    ]
    channel_catalog = [
        ("google-ads", "Paid Search"),
        ("facebook-ads", "Paid Social"),
        ("Emarsys", "Email"),
        ("attentive", "SMS"),
        ("impact", "Affiliate"),
        ("Direct", "Direct"),
        ("organic_and_social", "Organic"),
    ]

    channel_filter = params.get("channels")
    if channel_filter:
        channel_catalog = [c for c in channel_catalog if c[0] in channel_filter]

    season_filter = params.get("seasons")
    if season_filter:
        style_catalog = [s for s in style_catalog if s[2] in season_filter]

    style_filter = params.get("styles")
    if style_filter:
        style_catalog = [s for s in style_catalog if s[0] in style_filter]

    weeks_seen: set[tuple[int, int]] = set()
    iso_weeks: list[tuple[int, int]] = []
    for d in _date_range(params):
        iso_year, iso_week, _ = d.isocalendar()
        key = (iso_year, iso_week)
        if key not in weeks_seen:
            weeks_seen.add(key)
            iso_weeks.append(key)

    rows = []
    rng = random.Random(42)
    for iso_year, iso_week in iso_weeks:
        for vend_id, item_desc, season in style_catalog:
            for ch_source, ch_group in channel_catalog:
                base = 80 if ch_source in ("google-ads", "facebook-ads") else 30
                value = base + rng.randint(0, 200)
                rows.append({
                    "iso_year": iso_year,
                    "iso_week": iso_week,
                    "vend_id": vend_id,
                    "item_description": item_desc,
                    "season": season,
                    "channel_source": ch_source,
                    "channel_group": ch_group,
                    "value": value,
                })
    return rows


def _mock_amazon_receiving(params: dict) -> list[dict]:
    """Mock data for amazon_fba_receiving_by_sku snapshot metric."""
    statuses = params.get("statuses")
    fcs = params.get("fcs")
    base = [
        {"shipment_id": "FBA19D5P58YC", "shipment_name": "FBA STA (05/12/2026 17:52)-PBI3",
         "shipment_status": "RECEIVING", "destination_fc_id": "PBI3", "created_date": "2026-05-12",
         "seller_sku": "TMBAS9597RT-013-L", "fulfillment_network_sku": "B0916C5BKC",
         "quantity_shipped": 60, "quantity_received": 61, "quantity_in_case": 0, "receiving_gap": -1},
        {"shipment_id": "FBA19F2NMVJH", "shipment_name": "FBA STA (05/27/2026 16:16)-PBI3",
         "shipment_status": "READY_TO_SHIP", "destination_fc_id": "PBI3", "created_date": "2026-05-27",
         "seller_sku": "PACKBAG-001", "fulfillment_network_sku": "B0123ABCDE",
         "quantity_shipped": 100, "quantity_received": 0, "quantity_in_case": 0, "receiving_gap": 100},
    ]
    if statuses:
        base = [r for r in base if r["shipment_status"] in statuses]
    if fcs:
        base = [r for r in base if r["destination_fc_id"] in fcs]
    return base