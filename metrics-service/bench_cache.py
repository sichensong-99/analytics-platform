"""
Phase 5 — cache benchmark
Run from your metrics-service root:
    python bench_cache.py     (or: uv run python bench_cache.py)

Prints cold (loader / Databricks) vs warm (Redis) latency + the reduction %.
Out of the box it uses a PLACEHOLDER loader that simulates an ~800ms Databricks
query, so you can see the mechanism immediately. Swap in your real metric query
(one line) to get the real number for your resume.
"""
import time

try:
    from app.cache import benchmark, make_key      # if cache.py is at app/cache.py
except ImportError:
    from cache import benchmark, make_key           # if it's a sibling


# --- PLACEHOLDER loader: replace with your real query ----------------------
from app.databricks_client import run_query
from app.metrics_loader import get_metric

metric_id = "quantity_by_style_channel_week"

params = {
    "start_date": "2026-05-01",
    "end_date": "2026-05-31",
    "channels": None,
    "seasons": None,
    "styles": None,
}

metric = get_metric(metric_id)
if metric is None:
    raise RuntimeError(f"Metric not found: {metric_id}")

def loader():
    return run_query(metric["sql"], params)

key = make_key(metric_id, params)
result = benchmark(key, loader)

print(result)
if not result["cache_enabled"]:
    print("NOTE: Redis not reachable — start it with: docker run -d -p 6379:6379 redis")
else:
    print(f"\ncold (query): {result['cold_ms']} ms   warm (cache): {result['warm_ms']} ms"
          f"   -> {result['reduction_pct']}% faster per request")
