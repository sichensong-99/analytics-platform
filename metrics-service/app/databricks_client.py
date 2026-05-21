"""
Databricks Client (Mock for Phase 2A)

Phase 2A: returns mock data based on the SQL query.
Phase 3: will be replaced with real Databricks SQL connector.

The interface (run_query) stays the same, so callers don't change.
"""

import random
from datetime import date, timedelta
from typing import Any


def run_query(sql: str, params: dict[str, Any]) -> list[dict]:
    """
    Run a SQL query and return rows as a list of dicts.

    Phase 2A: This is a MOCK. It detects which metric is being queried
    based on keywords in the SQL and returns plausible fake data.
    """

    sql_lower = sql.lower()

    # Slice 1 new metric — most specific match first
    if "fact_orders_line" in sql_lower:
        return _mock_quantity_by_style_channel_week(params)
    # Existing 4 Phase 2A metrics
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
    Applies channels/seasons/styles filters server-side to match
    the eventual real-SQL behavior (filter pushdown).
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
    # (channel_source, legacy_channel_group)
    channel_catalog = [
        ("google-ads",   "Paid Search"),
        ("meta",         "Paid Social"),
        ("klaviyo",      "Email"),
        ("attentive",    "Email"),
        ("impact",       "Affiliates"),
        ("direct",       "Direct"),
        ("organic_and_social", "Organic Search"),
    ]

    # === Apply optional filters (parity with future real SQL) ===
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
            for (ch_source, legacy_grp) in channel_catalog:
                # Mock: Paid channels skew higher
                base = 80 if ch_source in ("google-ads", "meta") else 30
                value = base + rng.randint(0, 200)
                rows.append({
                    "iso_year": iso_year,
                    "iso_week": iso_week,
                    "vend_id": vend_id,
                    "item_description": item_desc,
                    "season": season,
                    "channel_source": ch_source,
                    "legacy_channel_group": legacy_grp,
                    "value": value,
                })
    return rows