# Databricks notebook source
# MAGIC %md
# MAGIC # Slice 1 — Notebook 04: Build `fact_orders_line` ⭐
# MAGIC
# MAGIC **Purpose**: Build the row-level sales fact table by joining Shopify order_line with
# MAGIC Triple Whale (TW) last-touch attribution and resolving against the three dim tables.
# MAGIC
# MAGIC **This is the technical centerpiece of Slice 1.** See `docs/architecture/slice_1_design.md`
# MAGIC §8 (Cross-source Join Strategy) for the full design rationale.
# MAGIC
# MAGIC **Inputs**:
# MAGIC - `mvdevdatabricks.shopify_32degrees.order`
# MAGIC - `mvdevdatabricks.shopify_32degrees.order_line`
# MAGIC - `mvdev_federated_catalog.triple_whale.attribution_order`
# MAGIC - `mvdev_federated_catalog.triple_whale.attribution_order_click`
# MAGIC - `mvdevdatabricks.analytics_platform_32degrees.dim_date`
# MAGIC - `mvdevdatabricks.analytics_platform_32degrees.dim_channel`
# MAGIC - `mvdevdatabricks.analytics_platform_32degrees.dim_product`
# MAGIC
# MAGIC **Output**: `mvdevdatabricks.analytics_platform_32degrees.fact_orders_line`
# MAGIC
# MAGIC **Idempotent**: Yes — full window rebuild via `mode("overwrite")` for slice 1. Phase 4
# MAGIC will introduce incremental daily append.
# MAGIC
# MAGIC **Author**: Sia Song
# MAGIC **Created**: 2026-05-19

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Configuration

# COMMAND ----------

from pyspark.sql import functions as F, Window

# ----- Target -----
TARGET_CATALOG = "mvdevdatabricks"
TARGET_SCHEMA = "analytics_platform_32degrees"
TARGET_TABLE = "fact_orders_line"
FULL_TARGET = f"{TARGET_CATALOG}.{TARGET_SCHEMA}.{TARGET_TABLE}"

# ----- Source tables -----
SHOPIFY_ORDER = "mvdevdatabricks.shopify_32degrees.order"
SHOPIFY_ORDER_LINE = "mvdevdatabricks.shopify_32degrees.order_line"
TW_ATTR_ORDER = "mvdev_federated_catalog.triple_whale.attribution_order"
TW_ATTR_ORDER_CLICK = "mvdev_federated_catalog.triple_whale.attribution_order_click"
DIM_DATE = f"{TARGET_CATALOG}.{TARGET_SCHEMA}.dim_date"
DIM_CHANNEL = f"{TARGET_CATALOG}.{TARGET_SCHEMA}.dim_channel"
DIM_PRODUCT = f"{TARGET_CATALOG}.{TARGET_SCHEMA}.dim_product"

# ----- Slice 1 ETL window (Decision 13: schema unbounded, ETL bounded) -----
ETL_START_DATE = "2025-07-01"

# ----- TW attribution model (Decision in design doc §8.3) -----
ATTRIBUTION_MODEL = "last_touch"

# ----- Timezone (32 Degrees operates from New York) -----
# Use Spark's DST-aware from_utc_timestamp with America/New_York timezone.
# This handles EST (UTC-5, winter) and EDT (UTC-4, summer) transitions automatically,
# correcting a known approximation in the legacy Panoply pipeline (which used a
# static UTC-5 offset year-round). See design doc §8.7.
BUSINESS_TIMEZONE = "America/New_York"

# ----- Run mode -----
# 'smoke'   = last 1 day only (for Day 3 morning quick check)
# 'full'    = full slice 1 window (for Day 3 afternoon production run)
RUN_MODE = "full"   # change to 'smoke' for quick validation pass

# ----- Multi-tier DQ thresholds -----
# Calibrated against empirically observed healthy baseline:
#   - TW <-> Shopify match rate >= 99.85% (validated across 11 months)
#   - i.e., baseline unmatched channel rate ~ 0.15%
#
# Channel resolution:
#   PASS  : unmatched < 0.5%   (~3x baseline buffer — normal variation tolerated)
#   WARN  : 0.5% <= unmatched < 2.0%   (operational signal, pipeline continues)
#   FAIL  : unmatched >= 2.0%   (~14x baseline — clear upstream anomaly, abort)
#
# Product resolution (looser; SKU drift from ERS upload cadence is more variable):
#   PASS  : unmatched < 1.0%
#   WARN  : 1.0% <= unmatched < 5.0%
#   FAIL  : unmatched >= 5.0%
#
# Row count range (sanity check on volume):
#   Expected ~10M rows for slice 1 window. Wide bounds for first-build tolerance.
CHANNEL_WARN_PCT = 0.005
CHANNEL_FAIL_PCT = 0.020
PRODUCT_WARN_PCT = 0.010
PRODUCT_FAIL_PCT = 0.050
ROW_COUNT_MIN = 8_000_000
ROW_COUNT_MAX = 12_000_000

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Define ETL window

# COMMAND ----------

if RUN_MODE == "smoke":
    # Smoke: last 24 hours only
    window_start_filter = F.expr("current_date() - INTERVAL 1 DAY")
    window_end_filter = F.expr("current_date()")
    print("[INFO] RUN_MODE=smoke — last 24 hours only")
else:
    window_start_filter = F.lit(ETL_START_DATE).cast("timestamp")
    window_end_filter = F.expr("current_timestamp()")
    print(f"[INFO] RUN_MODE=full — from {ETL_START_DATE} to now")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Read source tables

# COMMAND ----------

orders = (
    spark.table(SHOPIFY_ORDER)
         .filter(F.col("processed_at") >= window_start_filter)
         .filter(F.col("processed_at") < window_end_filter)
         .select(
             F.col("id").alias("order_id"),
             F.col("processed_at"),
         )
)

order_lines = (
    spark.table(SHOPIFY_ORDER_LINE)
         .select(
             F.col("id").alias("order_line_id"),
             F.col("order_id"),
             F.trim(F.col("sku")).alias("sku"),
             F.col("quantity"),
             F.col("price").alias("line_price"),
             F.col("total_discount"),
         )
)

print(f"[INFO] Orders in window: {orders.count():,}")
print(f"[INFO] Order_lines (unfiltered yet): {order_lines.count():,}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Build TW last-touch channel map
# MAGIC
# MAGIC See design doc §8.4 — dedup multi-row touchpoints to exactly one row per order
# MAGIC using a deterministic Window function.

# COMMAND ----------

# Filter attribution clicks to last_touch model only
last_touch_clicks_raw = (
    spark.table(TW_ATTR_ORDER_CLICK)
         .filter(F.col("attribution_model") == ATTRIBUTION_MODEL)
         .select(
             F.col("_triple_whale_order_id").alias("tw_order_id"),
             F.col("source").alias("channel_source"),
             F.col("position"),
             F.col("click_date"),
         )
)

print(f"[INFO] Last-touch click rows (raw): {last_touch_clicks_raw.count():,}")

# Deterministic dedup: max(position) tied by max(click_date)
w_dedup = (
    Window.partitionBy("tw_order_id")
          .orderBy(
              F.col("position").desc_nulls_last(),
              F.col("click_date").desc_nulls_last(),
          )
)

last_touch_per_order = (
    last_touch_clicks_raw
        .withColumn("rn", F.row_number().over(w_dedup))
        .filter(F.col("rn") == 1)
        .select("tw_order_id", "channel_source")
)

# Sanity: deduped rows must be unique by tw_order_id
deduped_count = last_touch_per_order.count()
distinct_tw_order_ids = last_touch_per_order.select("tw_order_id").distinct().count()
assert deduped_count == distinct_tw_order_ids, (
    f"Dedup failed: {deduped_count} rows but {distinct_tw_order_ids} distinct tw_order_ids"
)
print(f"[OK] Last-touch dedup: {deduped_count:,} unique order rows")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Join Shopify orders to TW last-touch channel

# COMMAND ----------

# Cast Shopify order.id (BIGINT) to STRING to match TW _triple_whale_order_id (STRING).
# See design doc §8.2 — this yields ≥ 99.85% match rate.
orders_with_channel = (
    orders
        .withColumn("order_id_str", F.col("order_id").cast("string"))
        .join(
            last_touch_per_order,
            F.col("order_id_str") == F.col("tw_order_id"),
            "left",
        )
        .select(
            F.col("order_id"),
            F.col("processed_at"),
            F.col("channel_source"),
        )
)

matched = orders_with_channel.filter(F.col("channel_source").isNotNull()).count()
total = orders_with_channel.count()
unmatched_pct = (total - matched) / total if total > 0 else 0
print(f"[INFO] Shopify ↔ TW order match: {matched:,}/{total:,} "
      f"({matched/total:.4%} matched, {unmatched_pct:.4%} unmatched)")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6. Compose pre-resolution fact (line × channel × processed_at)

# COMMAND ----------

# Inner-join order_line to orders_with_channel on order_id
fact_pre = (
    order_lines.alias("ol")
        .join(orders_with_channel.alias("o"), on="order_id", how="inner")
        .select(
            F.col("ol.order_line_id"),
            F.col("ol.order_id"),
            F.col("o.processed_at"),
            F.col("o.channel_source"),
            F.col("ol.sku"),
            F.col("ol.quantity"),
            F.col("ol.line_price"),
            F.col("ol.total_discount"),
        )
)

print(f"[INFO] Pre-resolution fact row count: {fact_pre.count():,}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 7. Derive `date_key` with DST-aware timezone normalization
# MAGIC
# MAGIC Per design doc §8.7 — `from_utc_timestamp` with `America/New_York` automatically handles
# MAGIC EST (UTC-5, winter) ↔ EDT (UTC-4, summer) DST transitions. This corrects the legacy
# MAGIC Panoply pipeline's known approximation (static UTC-5 year-round, ~1% systematic error
# MAGIC on summer-half cross-midnight orders).

# COMMAND ----------

fact_with_date = (
    fact_pre
        .withColumn(
            "processed_at_local",
            F.from_utc_timestamp(F.col("processed_at"), BUSINESS_TIMEZONE),
        )
        .withColumn(
            "date_key",
            F.date_format(F.col("processed_at_local"), "yyyyMMdd").cast("int"),
        )
        .drop("processed_at_local")
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 8. Resolve `channel_key` against `dim_channel`
# MAGIC
# MAGIC Left-join channel_source → dim_channel. Unmatched (NULL channel_source or
# MAGIC unseen value) resolves to `channel_key = -1`. See Decision 14 for the explicit
# MAGIC inclusion of Non-attributed / Excluded categories.

# COMMAND ----------

dim_channel = (
    spark.table(DIM_CHANNEL)
         .select("channel_key", "channel_source")
)

fact_with_channel = (
    fact_with_date
        .join(F.broadcast(dim_channel), on="channel_source", how="left")
        .withColumn("channel_key", F.coalesce(F.col("channel_key"), F.lit(-1)))
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 9. Resolve `product_key` against `dim_product`

# COMMAND ----------

dim_product = (
    spark.table(DIM_PRODUCT)
         .select("product_key", "sku")
)

fact_with_product = (
    fact_with_channel
        .join(F.broadcast(dim_product), on="sku", how="left")
        .withColumn("product_key", F.coalesce(F.col("product_key"), F.lit(-1)))
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 10. Validate `date_key` against `dim_date` (referential integrity)

# COMMAND ----------

dim_date = spark.table(DIM_DATE).select("date_key")

orphan_dates = (
    fact_with_product
        .join(F.broadcast(dim_date), on="date_key", how="left_anti")
        .select("date_key")
        .distinct()
)
orphan_count = orphan_dates.count()
if orphan_count > 0:
    print(f"[WARN] {orphan_count} fact date_keys not present in dim_date:")
    orphan_dates.show(20)
    raise AssertionError(
        "Fact contains date_keys outside dim_date range. "
        "Extend dim_date (regenerate generate_dim_date.py with wider range) or filter fact ETL window."
    )
else:
    print("[OK] All fact date_keys exist in dim_date")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 11. Final shape and multi-tier DQ assertions

# COMMAND ----------

fact_final = (
    fact_with_product
        .select(
            F.col("order_line_id"),
            F.col("order_id"),
            F.col("date_key"),
            F.col("channel_key"),
            F.col("product_key"),
            F.col("quantity"),
            F.col("line_price"),
            F.col("total_discount"),
            F.current_timestamp().alias("_ingest_at"),
        )
)

total_rows = fact_final.count()
print(f"[INFO] Final fact row count: {total_rows:,}")

# COMMAND ----------

def check_multi_tier(name: str, observed: float, warn: float, fail: float):
    """Multi-tier DQ check: PASS / WARN / FAIL based on thresholds."""
    if observed >= fail:
        msg = (
            f"[FAIL] {name}: {observed:.4%} >= FAIL threshold {fail:.4%}. "
            f"Aborting pipeline — investigate upstream data integrity before retry."
        )
        print(msg)
        raise AssertionError(msg)
    elif observed >= warn:
        print(
            f"[WARN] {name}: {observed:.4%} in WARN band [{warn:.4%}, {fail:.4%}). "
            f"Pipeline continues; review on next DQ report."
        )
    else:
        print(
            f"[OK]   {name}: {observed:.4%} < WARN threshold {warn:.4%}"
        )

# DQ-1: order_line_id PK uniqueness (hard fail — no tier, this must always hold)
distinct_ids = fact_final.select("order_line_id").distinct().count()
assert distinct_ids == total_rows, (
    f"order_line_id not unique: {total_rows} rows, {distinct_ids} distinct IDs"
)
print(f"[OK]   PK uniqueness: {distinct_ids:,} unique order_line_ids")

# DQ-2: channel resolution (multi-tier)
unresolved_channel = fact_final.filter(F.col("channel_key") == -1).count()
unresolved_channel_pct = unresolved_channel / total_rows if total_rows > 0 else 0
check_multi_tier(
    name=f"Unresolved channel ({unresolved_channel:,}/{total_rows:,})",
    observed=unresolved_channel_pct,
    warn=CHANNEL_WARN_PCT,
    fail=CHANNEL_FAIL_PCT,
)

# DQ-3: product resolution (multi-tier)
unresolved_product = fact_final.filter(F.col("product_key") == -1).count()
unresolved_product_pct = unresolved_product / total_rows if total_rows > 0 else 0
check_multi_tier(
    name=f"Unresolved product ({unresolved_product:,}/{total_rows:,})",
    observed=unresolved_product_pct,
    warn=PRODUCT_WARN_PCT,
    fail=PRODUCT_FAIL_PCT,
)

# DQ-4: row count sanity (only meaningful in full mode)
if RUN_MODE == "full":
    if not (ROW_COUNT_MIN <= total_rows <= ROW_COUNT_MAX):
        print(f"[WARN] Row count {total_rows:,} outside expected range "
              f"[{ROW_COUNT_MIN:,}, {ROW_COUNT_MAX:,}]. Continuing.")
    else:
        print(f"[OK]   Row count {total_rows:,} within expected range")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 12. Write Delta table (partitioned by date_key)

# COMMAND ----------

print(f"[INFO] Writing to {FULL_TARGET}")

(
    fact_final
        .write
        .format("delta")
        .mode("overwrite")
        .option("overwriteSchema", "true")
        .partitionBy("date_key")
        .saveAsTable(FULL_TARGET)
)

print(f"[OK] Write complete")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 13. Z-ORDER optimization
# MAGIC
# MAGIC Per design doc §10.2 — colocate by `channel_key, product_key` to speed up
# MAGIC drill-down matrix queries.

# COMMAND ----------

if RUN_MODE == "full":
    print(f"[INFO] Running OPTIMIZE ... ZORDER BY (channel_key, product_key)")
    spark.sql(f"OPTIMIZE {FULL_TARGET} ZORDER BY (channel_key, product_key)")
    print("[OK] Optimization complete")
else:
    print("[INFO] Skipping ZORDER in smoke mode")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 14. Post-write summary

# COMMAND ----------

written = spark.table(FULL_TARGET)
print(f"[INFO] Final table row count: {written.count():,}")

print("[INFO] Sample rows:")
written.orderBy(F.col("date_key").desc(), F.col("order_line_id")).limit(10).show(truncate=False)

print("[INFO] Daily row count (last 10 days in window):")
(
    written.groupBy("date_key")
           .count()
           .orderBy(F.col("date_key").desc())
           .limit(10)
           .show()
)

print("[INFO] Channel breakdown (top 10 by row count):")
(
    written.groupBy("channel_key")
           .count()
           .orderBy(F.col("count").desc())
           .limit(10)
           .show()
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 15. Summary
# MAGIC
# MAGIC | Metric | Value |
# MAGIC |---|---|
# MAGIC | Target | `mvdevdatabricks.analytics_platform_32degrees.fact_orders_line` |
# MAGIC | Grain | One row per Shopify order_line item |
# MAGIC | ETL window | 2025-07-01 → now |
# MAGIC | Attribution model | last_touch (Decision §8.3) |
# MAGIC | Partition | date_key |
# MAGIC | Z-ORDER | channel_key, product_key |
# MAGIC | Timezone | America/New_York via `from_utc_timestamp` (DST-aware) |
# MAGIC | DQ tiers | PASS / WARN / FAIL with calibrated thresholds |
# MAGIC | Idempotent | Yes — overwrite mode |
