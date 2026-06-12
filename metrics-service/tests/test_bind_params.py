"""Unit tests for databricks_client._bind_params — SQL parameter binding.
Pure functions: no FastAPI, no Databricks, no Redis."""
from datetime import date

from app.databricks_client import _bind_params


def test_date_params_become_yyyymmdd_int():
    sql = "SELECT * FROM t WHERE date_key BETWEEN :start_date AND :end_date"
    out, _ = _bind_params(sql, {"start_date": date(2025, 7, 1), "end_date": date(2025, 7, 31)})
    assert "20250701" in out and "20250731" in out
    assert ":start_date" not in out and ":end_date" not in out


def test_date_param_accepts_iso_string():
    out, _ = _bind_params("WHERE date_key >= :start_date", {"start_date": "2025-07-01"})
    assert "20250701" in out


def test_none_date_is_left_untouched():
    out, _ = _bind_params("WHERE date_key >= :start_date", {"start_date": None})
    assert ":start_date" in out


def test_empty_list_filter_collapses_to_null_guard():
    sql = "WHERE (:channels IS NULL OR channel IN (:channels))"
    out, _ = _bind_params(sql, {"channels": None})
    assert ":channels" not in out
    assert "NULL IS NULL" in out  # guard -> TRUE -> filter is a no-op


def test_empty_list_value_also_collapses():
    sql = "WHERE (:channels IS NULL OR channel IN (:channels))"
    out, _ = _bind_params(sql, {"channels": []})
    assert ":channels" not in out and "NULL" in out


def test_populated_list_filter_resolves_in_clause():
    sql = "WHERE (:channels IS NULL OR channel IN (:channels))"
    out, _ = _bind_params(sql, {"channels": ["google-ads", "meta"]})
    assert ":channels" not in out
    assert "FALSE" in out                       # :channels IS NULL -> FALSE
    assert "'google-ads'" in out and "'meta'" in out


def test_list_filter_escapes_single_quotes_sql_injection_guard():
    """A value with a quote must be escaped (doubled), not break out of the literal."""
    sql = "WHERE (:channels IS NULL OR channel IN (:channels))"
    out, _ = _bind_params(sql, {"channels": ["x'; DROP TABLE orders; --"]})
    assert "x''; DROP TABLE orders; --" in out      # quote doubled, stays inside literal
    assert "IN ('x'; DROP" not in out               # raw break-out form absent