"""
Databricks Client

Phase 2A: mock-only.
Day 4 (Slice 1): real Databricks SQL Warehouse connection added.

Mode is controlled by METRICS_DATA_SOURCE env var:
  - "databricks": query the real SQL Warehouse (default)
  - "mock":       return mock data (offline dev / demo fallback)

Auth is controlled by DATABRICKS_AUTH_TYPE env var:
  - "oauth": browser-based user login (no PAT needed; default)
  - "pat":   personal access token via DATABRICKS_TOKEN

The interface run_query(sql, params) is unchanged, so callers
(main.py) never change regardless of mode.
"""

import os
import random
from datetime import date, timedelta
from typing import Any

from dotenv import load_dotenv

load_dotenv()

DATA_SOURCE = os.getenv("METRICS_DATA_SOURCE", "databricks").lower()


# ============ Public interface ============

def run_query(sql: str, params: dict[str, Any]) -> list[dict]:
    """
    Run a SQL query and return rows as a list of dicts.

    Dispatches to the real Databricks connector or the mock generator
    based on METRICS_DATA_SOURCE.
    """
    if DATA_SOURCE == "mock":
        return _run_query_mock(sql, params)

    try:
        return _run_query_databricks(sql, params)
    except Exception as e:
        # Surface the error clearly; caller (main.py) maps it to a 500.
        raise RuntimeError(f"Databricks query failed: {e}") from e


# ============ Real Databricks connection ============

def _run_query_databricks(sql: str, params: dict[str, Any]) -> list[dict]:
    """
    Execute the metric SQL against the Databricks SQL Warehouse.

    Auth mode is controlled by DATABRICKS_AUTH_TYPE:
      - "oauth": browser-based U2M login (no PAT needed; default)
      - "pat":   personal access token via DATABRICKS_TOKEN

    Named params (:start_date, :channels, ...) are passed via the
    connector's native parameter binding, which prevents SQL injection.
    """
    from databricks import sql as dbsql

    hostname = os.environ["DATABRICKS_SERVER_HOSTNAME"]
    http_path = os.environ["DATABRICKS_HTTP_PATH"]
    auth_type = os.getenv("DATABRICKS_AUTH_TYPE", "oauth").lower()

    bound_sql, bound_params = _bind_params(sql, params)

    connect_kwargs: dict[str, Any] = {
        "server_hostname": hostname,
        "http_path": http_path,
    }
    if auth_type == "pat":
        connect_kwargs["access_token"] = os.environ["DATABRICKS_TOKEN"]
    else:
        # OAuth user-to-machine: opens a browser on first connect,
        # caches credentials locally afterward.
        connect_kwargs["auth_type"] = "databricks-oauth"

    with dbsql.connect(**connect_kwargs) as connection:
        with connection.cursor() as cursor:
            cursor.execute(bound_sql, bound_params)
            columns = [c[0] for c in cursor.description]
            rows = cursor.fetchall()

    return [dict(zip(columns, row)) for row in rows]


def _bind_params(sql: str, params: dict[str, Any]) -> tuple[str, dict]:
    """
    Adapt our metric params to the SQL Warehouse before execution.

    Why this is non-trivial:
    - date_key in dim_date is BIGINT (e.g. 20250901), but the API passes
      Python date objects. A date->BIGINT cast fails, so we must convert
      date values destined for :start_date / :end_date into the integer
      yyyyMMdd form.
    - The metric SQL uses the (:x IS NULL OR col IN (:x)) guard pattern
      for optional filters. Rather than rely on the connector's named-
      parameter list expansion (fragile for IN clauses), we resolve all
      markers into safe inline SQL here:
        * None        -> the whole guard collapses to (TRUE)
        * list value  -> expanded into a quoted IN (...) literal list
        * date value  -> integer yyyyMMdd literal
    The result is a fully-resolved SQL string with no bind markers.
    """
    # Params that filter date_key (BIGINT yyyyMMdd) — convert date -> int.
    DATE_KEY_PARAMS = {"start_date", "end_date"}
    # Optional list filters that use the (:x IS NULL OR col IN (:x)) guard.
    LIST_GUARD_PARAMS = {"channels", "seasons", "styles"}

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
        if not value:  # None or empty list -> guard collapses to TRUE
            # (:x IS NULL OR col IN (:x))  ->  (NULL IS NULL OR col IN (NULL))
            out_sql = out_sql.replace(marker, "NULL")
        else:
            # Build a safe quoted literal list. Single quotes escaped.
            safe_items = [str(v).replace("'", "''") for v in value]
            in_list = ", ".join(f"'{item}'" for item in safe_items)
            # First marker (the `:x IS NULL` test) -> a non-NULL sentinel
            # so the guard does NOT short-circuit; second -> the IN list.
            out_sql = out_sql.replace(f"{marker} IS NULL", "FALSE", 1)
            out_sql = out_sql.replace(marker, in_list)

    # All markers resolved inline; no bind params remain.
    return out_sql, {}


# ============ Mock dispatch (offline / demo fallback) ============

def _run_query_mock(sql: str, params: dict[str, Any]) -> list[dict]:
    """Detect which metric is queried by SQL keywords, return fake data."""
    sql_lower = sql.lower()

    if "fact_orders_line" in sql_lower:
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
    """Build a list of dates from start_date to end_date (inclusive)."""
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
    """
    Mock data for Slice 1 quantity_by_style_channel_week.
    Channel values aligned with dim_channel v2.0 real seed values.
    """
    # (vend_id, item_description, season)
    style_catalog = [
        ("PACKBAG",      "Packable Backpack",         "F23"),
        ("SILVERTOTE",   "Silver Tote",               "F23"),
        ("T3FK1451PRT",  "Printed Fleece Pullover",   "F22"),
        ("HEATER100",    "Heated Vest",               "F23"),
        ("WAFFLEHOOD",   "Waffle Knit Hoodie",        "F22"),
        ("STORMBOOT",    "Storm Boot",                "F23"),
    ]
    # (channel_source, channel_group) — aligned with dim_channel v2.0
    channel_catalog = [
        ("google-ads",          "Paid Search"),
        ("facebook-ads",        "Paid Social"),
        ("Emarsys",             "Email"),
        ("attentive",           "SMS"),
        ("impact",              "Affiliate"),
        ("Direct",              "Direct"),
        ("organic_and_social",  "Organic"),
    ]

    # === Apply optional filters (parity with real SQL) ===
    channel_filter = params.get("channels")
    if channel_filter:
        channel_catalog = [c for c in channel_catalog if c[0] in channel_filter]

    season_filter = params.get("seasons")
    if season_filter:
        style_catalog = [s for s in style_catalog if s[2] in season_filter]

    style_filter = params.get("styles")
    if style_filter:
        style_catalog = [s for s in style_catalog if s[0] in style_filter]

    # === Build distinct (iso_year, iso_week) tuples from date range ===
    weeks_seen: set = set()
    iso_weeks: list[tuple[int, int]] = []
    for d in _date_range(params):
        iso_year, iso_week, _ = d.isocalendar()
        key = (iso_year, iso_week)
        if key not in weeks_seen:
            weeks_seen.add(key)
            iso_weeks.append(key)

    # === Generate rows: week × style × channel ===
    rows = []
    rng = random.Random(42)  # Deterministic for demo
    for (iso_year, iso_week) in iso_weeks:
        for (vend_id, item_desc, season) in style_catalog:
            for (ch_source, ch_group) in channel_catalog:
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