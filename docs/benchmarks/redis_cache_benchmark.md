# Redis Cache Benchmark — Production-validated

**Date:** 2026-06-11
**Setup:** local Redis (docker redis:7-alpine) + live Databricks Serverless warehouse (2X-Small),
metric = quantity_by_style_channel_week, date range 2026-05-01..2026-05-31, via bench_cache.py.

## Result
| call | latency | meaning |
|---|---|---|
| cold (cache miss) | **5086.0 ms** | real query against ~10M-row fact on serverless warehouse |
| warm (cache hit)  | **16.6 ms**   | served from Redis (cache-aside) |
| per-request reduction | **99.7%** | for a repeated identical query within TTL |

## How to read this
- The 99.7% is the **per-repeated-request** speedup, NOT an average production saving.
- Average production saving depends on the **cache hit rate** (to be measured via request-level
  instrumentation in the observability work). Cold path is genuinely ~5s because it scans the
  full fact table; warm path is an in-memory Redis hit (~17ms incl. serialization).
- Cache is **cache-aside with graceful degradation**: Redis down -> fall back to direct query,
  never a hard dependency (verified — service runs with Redis absent).

