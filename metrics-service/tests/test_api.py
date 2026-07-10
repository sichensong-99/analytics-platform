"""Integration tests on the full app: import, health, 404/422 contracts, auth gate.
If these fail in CI, the import chain (auth/cache/loader) needs an env var — read
the traceback and send me auth.py / metrics_loader.py."""


def test_app_imports():
    from app.main import app
    assert app.title


def test_health_no_auth(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_list_metrics_with_auth(client):
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_unknown_metric_returns_404(client):
    resp = client.get("/metrics/__no_such_metric__",
                      params={"start_date": "2025-07-01", "end_date": "2025-07-31"})
    assert resp.status_code == 404


def test_unknown_snapshot_returns_404(client):
    assert client.get("/snapshot/__no_such__").status_code == 404


def test_missing_date_params_returns_422(client):
    # start_date / end_date are required query params
    assert client.get("/metrics/anything").status_code == 422


def test_metrics_requires_auth():
    # raw client, NO auth override -> real auth must reject
    from fastapi.testclient import TestClient
    from app.main import app
    app.dependency_overrides.clear()
    resp = TestClient(app).get("/metrics")
    assert resp.status_code in (401, 403)