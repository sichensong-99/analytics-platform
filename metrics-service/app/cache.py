"""
Phase 5 — Redis caching layer (cache-aside)

Wrap any metric query so repeated calls hit Redis instead of Databricks.
Graceful: if Redis is unreachable, it just runs the query directly — the cache
is an optimization, never a hard dependency.

Setup:
    pip install redis        (or: uv add redis)
    docker run -d -p 6379:6379 redis        # local Redis, one line
    # set REDIS_URL if not on localhost:  REDIS_URL=redis://host:6379

Drop-in: save as app/cache.py and wrap your metric query (see bench_cache.py).
"""
import hashlib
import json
import os
import time
from typing import Any, Callable

REDIS_URL   = os.environ.get("REDIS_URL", "redis://localhost:6379")
DEFAULT_TTL = int(os.environ.get("CACHE_TTL_SECONDS", "300"))   # 5 min

_client = None
_checked = False


def _redis():
    """Lazy Redis client; returns None if redis isn't installed/reachable."""
    global _client, _checked
    if _checked:
        return _client
    _checked = True
    try:
        import redis
        c = redis.Redis.from_url(REDIS_URL, socket_connect_timeout=1, decode_responses=True)
        c.ping()
        _client = c
    except Exception:
        _client = None     # -> no-cache fallback, service keeps working
    return _client


def make_key(metric: str, params: dict | None = None) -> str:
    """Deterministic cache key from a metric name + its params/filters."""
    blob = json.dumps(params or {}, sort_keys=True, default=str)
    digest = hashlib.sha1(blob.encode()).hexdigest()[:16]
    return f"metric:{metric}:{digest}"


def cached_query(key: str, loader: Callable[[], Any], ttl: int = DEFAULT_TTL):
    """Cache-aside: return cached value if present, else run loader(), store, return."""
    r = _redis()
    if r is not None:
        try:
            hit = r.get(key)
            if hit is not None:
                return json.loads(hit)
        except Exception:
            pass                      # any cache error -> treat as a miss
    value = loader()                  # <-- the real (slow) query runs here
    if r is not None:
        try:
            r.setex(key, ttl, json.dumps(value, default=str))
        except Exception:
            pass
    return value


def invalidate(key: str):
    r = _redis()
    if r is not None:
        try:
            r.delete(key)
        except Exception:
            pass


def benchmark(key: str, loader: Callable[[], Any], ttl: int = DEFAULT_TTL) -> dict:
    """Time a cold call (miss -> loader) vs a warm call (hit -> Redis)."""
    invalidate(key)
    t0 = time.perf_counter()
    cached_query(key, loader, ttl)        # cold: runs loader, fills cache
    cold_ms = (time.perf_counter() - t0) * 1000
    t1 = time.perf_counter()
    cached_query(key, loader, ttl)        # warm: served from Redis
    warm_ms = (time.perf_counter() - t1) * 1000
    reduction = (1 - warm_ms / cold_ms) * 100 if cold_ms else 0
    return {
        "cold_ms": round(cold_ms, 1),
        "warm_ms": round(warm_ms, 1),
        "reduction_pct": round(reduction, 1),
        "cache_enabled": _redis() is not None,
    }
