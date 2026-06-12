"""Integration tests using real metric ids from definitions.yaml.
Relies on the `client` fixture (auth bypassed, cache passthrough, mock data source)."""


def test_real_metric_happy_path(client):
    resp = client.get(
        "/metrics/quantity_by_style_channel_week",
        params={"start_date": "2025-07-01", "end_date": "2025-07-31"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["metric_id"] == "quantity_by_style_channel_week"
    assert isinstance(body["data"], list)
    assert "params" in body


def test_real_metric_date_range_echoed(client):
    resp = client.get(
        "/metrics/quantity_by_style_channel_week",
        params={"start_date": "2025-07-01", "end_date": "2025-07-31"},
    )
    assert resp.json()["params"]["start_date"] == "2025-07-01"


def test_real_metric_end_before_start_400(client):
    resp = client.get(
        "/metrics/quantity_by_style_channel_week",
        params={"start_date": "2025-07-31", "end_date": "2025-07-01"},
    )
    assert resp.status_code == 400


def test_real_metric_optional_filters_pass_through(client):
    resp = client.get(
        "/metrics/quantity_by_style_channel_week",
        params={
            "start_date": "2025-07-01", "end_date": "2025-07-31",
            "channels": ["google-ads", "facebook-ads"],
        },
    )
    assert resp.status_code == 200
    assert resp.json()["params"]["channels"] == ["google-ads", "facebook-ads"]


def test_snapshot_metric_happy_path(client):
    # amazon_fba_receiving_by_sku is a snapshot metric (no date range)
    resp = client.get("/snapshot/amazon_fba_receiving_by_sku")
    assert resp.status_code == 200
    body = resp.json()
    assert body["metric_id"] == "amazon_fba_receiving_by_sku"
    assert isinstance(body["data"], list)


def test_catalog_lists_active_only(client):
    # deprecated metrics (revenue_by_day etc.) must not appear
    resp = client.get("/catalog")
    assert resp.status_code == 200
    keys = {m["key"] for m in resp.json()["metrics"]}
    assert "quantity_by_style_channel_week" in keys
    assert "revenue_by_day" not in keys   # deprecated -> filtered