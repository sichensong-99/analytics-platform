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

    # Detect metric type from SQL content
    if "daily_revenue" in sql_lower and "order_count" in sql_lower:
        return _mock_aov_by_day(params)
    elif "daily_revenue" in sql_lower:
        return _mock_revenue_by_day(params)
    elif "channel_performance" in sql_lower and "ad_spend" in sql_lower and "group by event_date" in sql_lower:
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
        {
            "date": d.isoformat(),
            "value": round(random.uniform(3000, 8000), 2),
        }
        for d in _date_range(params)
    ]


def _mock_aov_by_day(params: dict) -> list[dict]:
    return [
        {
            "date": d.isoformat(),
            "value": round(random.uniform(80, 180), 2),
        }
        for d in _date_range(params)
    ]


def _mock_roas_by_channel(params: dict) -> list[dict]:
    channels = ["Facebook", "Google", "TikTok", "Email", "Organic"]
    return [
        {
            "channel": ch,
            "value": round(random.uniform(2.5, 5.5), 2),
        }
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