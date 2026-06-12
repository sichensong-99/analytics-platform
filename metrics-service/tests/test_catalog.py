"""Catalog tests: pure _normalize/_mock helpers + the /catalog endpoint mounted
in isolation (no auth dependency)."""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers.catalog import _normalize, _mock, router


def test_normalize_maps_field_aliases():
    out = _normalize("rev", {
        "name": "Revenue", "desc": "net of refunds", "ver": 2,
        "sql": "SUM(net_amount)", "format": "USD", "team": "analytics",
    })
    assert out["key"] == "rev"
    assert out["label"] == "Revenue"
    assert out["description"] == "net of refunds"
    assert out["version"] == 2
    assert out["definition"] == "SUM(net_amount)"
    assert out["unit"] == "USD"
    assert out["owner"] == "analytics"
    assert out["status"] == "active"


def test_normalize_defaults_label_to_key():
    out = _normalize("orphan_metric", {})
    assert out["label"] == "orphan_metric"
    assert out["status"] == "active"


def test_mock_has_expected_shape():
    rows = _mock()
    assert isinstance(rows, list) and rows
    assert all("key" in m and "label" in m for m in rows)


def test_catalog_endpoint_returns_only_active_metrics():
    test_app = FastAPI()
    test_app.include_router(router)
    c = TestClient(test_app)

    resp = c.get("/catalog")
    assert resp.status_code == 200
    body = resp.json()
    for field in ("source", "count", "metrics", "filters"):
        assert field in body
    assert all((m.get("status") or "active") == "active" for m in body["metrics"])
    assert body["count"] == len(body["metrics"])