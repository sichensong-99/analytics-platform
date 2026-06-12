"""Shared fixtures + env setup for the metrics-service test suite."""
import os

# Force offline/mock behavior BEFORE any app module imports.
# databricks_client reads METRICS_DATA_SOURCE at import; auth reads JWT_SECRET.
os.environ.setdefault("METRICS_DATA_SOURCE", "mock")
os.environ.setdefault("JWT_SECRET", "test-secret-not-for-production")

import pytest


@pytest.fixture
def client():
    """Full-app TestClient with auth bypassed and the cache made a passthrough.

    - get_current_user overridden  -> endpoints don't need a real JWT
    - cached_query -> direct call   -> no Redis needed
    - METRICS_DATA_SOURCE=mock       -> run_query returns mock rows, no Databricks
    """
    from types import SimpleNamespace
    from fastapi.testclient import TestClient

    import app.main as main_module
    from app.main import app
    from app.auth import get_current_user

    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        sub="test-user", username="test-user", role="admin"
    )

    saved = main_module.cached_query
    main_module.cached_query = lambda key, fn: fn()
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.clear()
        main_module.cached_query = saved