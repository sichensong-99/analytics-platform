# Databricks notebook source
# MAGIC %md
# MAGIC # Searchspring Collection-Position — Daily Snapshot (minimal logging job)
# MAGIC
# MAGIC **Why this exists:** product position in a Searchspring collection is a time series
# MAGIC with NO backfill — the source keeps no history, so any day we don't capture is gone
# MAGIC forever. This job snapshots the served order daily and locks it to the date, so the
# MAGIC history exists when the position×performance analysis is built later (parked for now).
# MAGIC
# MAGIC **Scope (deliberately minimal):** capture ONLY what Searchspring uniquely produces —
# MAGIC the merchandising decision (position + pin/boost/remove flags). Everything else
# MAGIC (sku, name, price, inventory, images, days_since_published, boost_reason) is Shopify
# MAGIC data and is joined / derived at analysis time by `product_id`. This is a logging job,
# MAGIC not a modeled gold table: no medallion layers, no DQ gate, no reconciliation.
# MAGIC
# MAGIC **Run:** daily ~10am ET (after manual curation, before peak). Idempotent — re-running
# MAGIC the same day overwrites that day's partition (no duplicate rows).
# MAGIC
# MAGIC **API:** public Searchspring (Athos) Category API. Plain HTTPS GET, JSON back.
# MAGIC No key / token / OAuth — `siteId` is the only credential.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Config

# COMMAND ----------

# --- Target tables (matches the spec's names; rename fct_ -> fact_ if you want
#     platform-naming consistency with fact_orders_line etc.) ---
TARGET_CATALOG = "analytics_catalog"
TARGET_SCHEMA = "analytics_platform"
FCT_TABLE = f"{TARGET_CATALOG}.{TARGET_SCHEMA}.fct_collection_position"          # per product / collection / day
META_TABLE = f"{TARGET_CATALOG}.{TARGET_SCHEMA}.fct_collection_position_meta"    # per collection / day (snapshot context)

# --- Searchspring API ---
SITE_ID = "abc123"
BASE_URL = f"https://{SITE_ID}.a.searchspring.io/api/search/category.json"
DOMAIN_BASE = "https://www.example.com/collections"
RESULTS_PER_PAGE = 100
REQUEST_TIMEOUT = 30
POLITE_SLEEP_SECONDS = 0.2   # endpoint has no real rate limit; tiny pause just to be polite

# --- Collections to snapshot ---
# Option A (default): a configured list. Fill with your merchandised collection handles.
COLLECTION_HANDLES = [
    "womens",
    "mens",
    "new-arrivals",
    "sale",
    # ... add the rest of your merchandised collection handles ...
]

# Option B (self-maintaining): derive the list from your Shopify collections table,
# so new collections are picked up automatically. Uncomment if that table exists:
# COLLECTION_HANDLES = [r["handle"] for r in spark.sql(
#     "SELECT DISTINCT handle FROM dpsync.shopify_raw.collection"
# ).collect()]

print(f"[INFO] Snapshotting {len(COLLECTION_HANDLES)} collections")
print(f"[INFO] Target: {FCT_TABLE}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Helpers

# COMMAND ----------

import uuid
import time
import json
import requests
from datetime import datetime
from zoneinfo import ZoneInfo
from pyspark.sql import functions as F, types as T

ET = ZoneInfo("America/New_York")


def _fetch_page(handle: str, page: int) -> dict:
    """One HTTPS GET for one page of one collection. Fresh UUIDs each call (API requires them)."""
    params = {
        "siteId": SITE_ID,
        "resultsFormat": "json",
        "bgfilter.collection_handle": handle,
        "domain": f"{DOMAIN_BASE}/{handle}",
        "resultsPerPage": RESULTS_PER_PAGE,
        "page": page,
        "userId": str(uuid.uuid4()),
        "sessionId": str(uuid.uuid4()),
        "pageLoadId": str(uuid.uuid4()),
    }
    resp = requests.get(BASE_URL, params=params, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def _id_set(merch: dict, key: str) -> set:
    """
    Build a set of result-id hashes from a merchandising array
    (elevated / is_elevated / removed). Handles either list-of-strings or
    list-of-dicts. NOTE: the flags match on the result `id` hash, NOT on `uid`.
    """
    out = set()
    for el in (merch or {}).get(key) or []:
        if isinstance(el, dict):
            v = el.get("id", el.get("uid"))
            if v is not None:
                out.add(str(v))
        else:
            out.add(str(el))
    return out


def snapshot_collection(handle: str):
    """Pull the full ranking for one collection (all pages). Returns (product_rows, meta_dict)."""
    rows = []

    first = _fetch_page(handle, 1)
    pagination = first.get("pagination", {}) or {}
    total_pages = int(pagination.get("totalPages") or 1)
    total_results = int(pagination.get("totalResults") or 0)
    default_per_page = int(pagination.get("defaultPerPage") or RESULTS_PER_PAGE)

    merch0 = first.get("merchandising", {}) or {}
    triggered = merch0.get("triggeredCampaigns")

    default_sort = None
    for opt in (first.get("sorting", {}) or {}).get("options", []) or []:
        if opt.get("selected") or opt.get("default"):
            default_sort = opt.get("field") or opt.get("label")
            break

    position = 0  # 1-based rank, continued across pages

    def _consume(payload: dict):
        nonlocal position
        m = payload.get("merchandising", {}) or {}
        pinned, boosted, removed = _id_set(m, "elevated"), _id_set(m, "is_elevated"), _id_set(m, "removed")
        for res in payload.get("results", []) or []:
            position += 1
            rid = str(res.get("id")) if res.get("id") is not None else None
            rows.append((
                handle,
                str(res.get("uid")) if res.get("uid") is not None else None,  # product_id
                position,
                bool(rid in pinned) if rid else False,
                bool(rid in boosted) if rid else False,
                bool(rid in removed) if rid else False,
            ))

    _consume(first)
    for p in range(2, total_pages + 1):
        time.sleep(POLITE_SLEEP_SECONDS)
        _consume(_fetch_page(handle, p))

    meta = (
        handle,
        total_results,
        default_per_page,
        default_sort,
        json.dumps(triggered) if triggered is not None else None,
    )
    return rows, meta

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Fetch all collections
# MAGIC One bad collection won't kill the run — it's logged and skipped.

# COMMAND ----------

now_et = datetime.now(ET)
snapshot_date = now_et.date().isoformat()      # ET calendar date of this run
snapshot_ts = now_et.replace(tzinfo=None)      # naive ET timestamp for the row

all_rows, all_meta, failures = [], [], []

for handle in COLLECTION_HANDLES:
    try:
        rows, meta = snapshot_collection(handle)
        all_rows.extend(rows)
        all_meta.append(meta)
        print(f"[OK]   {handle}: {len(rows)} products")
    except Exception as e:
        failures.append((handle, str(e)))
        print(f"[WARN] {handle} failed (skipped): {e}")

print(f"\n[INFO] Snapshot {snapshot_date}: {len(all_rows)} rows across "
      f"{len(all_meta)} collections, {len(failures)} failed")

if not all_rows:
    raise RuntimeError(
        "No rows fetched. Check (a) collection handles, (b) outbound HTTPS egress "
        "from this cluster, (c) the API is reachable."
    )

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Write (idempotent — overwrites today's partition on re-run)

# COMMAND ----------

pos_schema = T.StructType([
    T.StructField("collection_handle", T.StringType()),
    T.StructField("product_id", T.StringType()),
    T.StructField("position", T.IntegerType()),
    T.StructField("is_pinned", T.BooleanType()),
    T.StructField("is_boosted", T.BooleanType()),
    T.StructField("is_removed", T.BooleanType()),
])

df_pos = (
    spark.createDataFrame(all_rows, schema=pos_schema)
    .withColumn("snapshot_date", F.lit(snapshot_date).cast("date"))
    .withColumn("snapshot_ts", F.lit(snapshot_ts.isoformat()).cast("timestamp"))
    .select("snapshot_date", "snapshot_ts", "collection_handle",
            "product_id", "position", "is_pinned", "is_boosted", "is_removed")
)

(
    df_pos.write.format("delta").mode("overwrite")
    .option("replaceWhere", f"snapshot_date = '{snapshot_date}'")  # re-run safe: replaces just today
    .option("mergeSchema", "true")
    .partitionBy("snapshot_date")
    .saveAsTable(FCT_TABLE)
)
print(f"[OK] wrote {df_pos.count()} rows to {FCT_TABLE} (snapshot_date={snapshot_date})")

# --- companion: per-collection snapshot context ---
meta_schema = T.StructType([
    T.StructField("collection_handle", T.StringType()),
    T.StructField("total_results", T.IntegerType()),
    T.StructField("default_per_page", T.IntegerType()),
    T.StructField("default_sort", T.StringType()),
    T.StructField("triggered_campaigns", T.StringType()),
])

df_meta = (
    spark.createDataFrame(all_meta, schema=meta_schema)
    .withColumn("snapshot_date", F.lit(snapshot_date).cast("date"))
    .withColumn("snapshot_ts", F.lit(snapshot_ts.isoformat()).cast("timestamp"))
    .select("snapshot_date", "snapshot_ts", "collection_handle",
            "total_results", "default_per_page", "default_sort", "triggered_campaigns")
)

(
    df_meta.write.format("delta").mode("overwrite")
    .option("replaceWhere", f"snapshot_date = '{snapshot_date}'")
    .option("mergeSchema", "true")
    .partitionBy("snapshot_date")
    .saveAsTable(META_TABLE)
)
print(f"[OK] wrote {df_meta.count()} rows to {META_TABLE}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Quick look

# COMMAND ----------

print("Top of each collection today (position 1-5):")
spark.table(FCT_TABLE) \
    .filter(F.col("snapshot_date") == F.lit(snapshot_date)) \
    .filter(F.col("position") <= 5) \
    .orderBy("collection_handle", "position") \
    .show(50, truncate=False)

if failures:
    print("Collections that failed this run (re-run is safe; it overwrites today):")
    for h, err in failures:
        print(f"  - {h}: {err}")
