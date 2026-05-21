# MAGIC **Run mode**: FULL REBUILD / BACKFILL only.
# MAGIC Not for daily incremental loads. Incremental version (watermark +
# MAGIC 2-day lookback) is implemented in Phase 4 — see phase4_orchestration_design.md.

# Databricks notebook source
# MAGIC %md
# MAGIC # Slice 1 — Notebook 04: Build `fact_orders_line`
# MAGIC # Classic Compute Full Rebuild Version
# MAGIC
# MAGIC **Purpose**: Join Shopify order lines with Triple Whale click attribution
# MAGIC and conformed dimensions to produce the row-grain sales fact table for Slice 1.
# MAGIC
# MAGIC **Compute target**
# MAGIC - This version is intended for Personal Compute / Classic Compute.
# MAGIC - It uses DataFrame cache, which Serverless compute did not support.
# MAGIC
# MAGIC **Key logic**
# MAGIC - Uses `attribution_order_click`, not `attribution_order`.
# MAGIC - Uses `_triple_whale_order_id` as TW order join key.
# MAGIC - Uses `source` as TW channel source.
# MAGIC - Uses `position DESC, click_date DESC` for TW last-touch deduplication.
# MAGIC - Adds conservative source normalization before `dim_channel` join.
# MAGIC - Combines TW join diagnostics into one aggregation.
# MAGIC - Combines DQ metrics into one aggregation.
# MAGIC - Caches `fact_raw` before DQ and write.
# MAGIC - Uses `NUM_WRITE_PARTITIONS = 32`, suitable for small Personal Compute.

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Configuration

# COMMAND ----------

from pyspark.sql import functions as F
from pyspark.sql.window import Window

# --- Source tables ---
SHOPIFY_CATALOG = "mvdevdatabricks"
SHOPIFY_SCHEMA = "shopify_32degrees"

TW_CATALOG = "mvdev_federated_catalog"
TW_SCHEMA = "triple_whale"
TW_ATTRIBUTION_CLICK_TABLE = "attribution_order_click"

# --- Target ---
TARGET_CATALOG = "mvdevdatabricks"
TARGET_SCHEMA = "analytics_platform_32degrees"
TARGET_TABLE = "fact_orders_line"
FULL_TARGET = f"{TARGET_CATALOG}.{TARGET_SCHEMA}.{TARGET_TABLE}"

# --- Dims ---
DIM_DATE = f"{TARGET_CATALOG}.{TARGET_SCHEMA}.dim_date"
DIM_PRODUCT = f"{TARGET_CATALOG}.{TARGET_SCHEMA}.dim_product"
DIM_CHANNEL = f"{TARGET_CATALOG}.{TARGET_SCHEMA}.dim_channel"

# --- ETL window ---
# Full rebuild mode. Do not use this daily unless intentionally rebuilding history.
ETL_START = "2025-07-01"
ETL_END = "2099-12-31"

# --- DQ SLO thresholds ---
DQ_CHANNEL_WARN_PCT = 0.005   # 0.5%
DQ_CHANNEL_FAIL_PCT = 0.020   # 2.0%

DQ_PRODUCT_WARN_PCT = 0.010   # 1.0%
DQ_PRODUCT_FAIL_PCT = 0.050   # 5.0%

# --- Performance knobs ---
# Personal compute is small, so do not use 400 partitions.
# 32 is more appropriate for a 4-core cluster.
NUM_WRITE_PARTITIONS = 32

# Keep False to avoid extra full-table scans after write.
RUN_POST_WRITE_VALIDATION = False

try:
    spark.conf.set("spark.sql.shuffle.partitions", str(NUM_WRITE_PARTITIONS))
    print(f"[INFO] spark.sql.shuffle.partitions set to {NUM_WRITE_PARTITIONS}")
except Exception as e:
    print(f"[WARN] Could not set spark.sql.shuffle.partitions: {e}")

print("[INFO] Configuration loaded")
print(f"[INFO] Target table: {FULL_TARGET}")
print(f"[INFO] ETL window: {ETL_START} -> {ETL_END}")
print(f"[INFO] Write repartition count: {NUM_WRITE_PARTITIONS}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Load source tables

# COMMAND ----------

print("[INFO] Loading source tables ...")

orders = spark.table(f"{SHOPIFY_CATALOG}.{SHOPIFY_SCHEMA}.order").alias("o")
order_lines = spark.table(f"{SHOPIFY_CATALOG}.{SHOPIFY_SCHEMA}.order_line").alias("ol")

aoc = spark.table(
    f"{TW_CATALOG}.{TW_SCHEMA}.{TW_ATTRIBUTION_CLICK_TABLE}"
).alias("aoc")

dim_date = spark.table(DIM_DATE).alias("dd")
dim_product = spark.table(DIM_PRODUCT).alias("dp")
dim_channel = spark.table(DIM_CHANNEL).alias("dc")

print("[INFO] Source tables loaded")
print("[INFO] TW attribution_order_click columns:")
print(aoc.columns)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Prepare Shopify order lines

# COMMAND ----------

print("[INFO] Preparing Shopify order lines ...")

ol_with_date = order_lines.join(
    orders.select(
        F.col("o.id").alias("order_id_hdr"),
        F.col("o.name").alias("shopify_order_name"),
        F.col("o.processed_at").alias("processed_at"),
        F.col("o.financial_status").alias("financial_status"),
    ),
    on=F.col("ol.order_id") == F.col("order_id_hdr"),
    how="inner",
)

# DST-aware UTC -> Eastern conversion.
# Shopify processed_at is treated as UTC and converted to America/New_York.
ol_with_date = ol_with_date.withColumn(
    "order_date_eastern",
    F.from_utc_timestamp(F.col("processed_at"), "America/New_York"),
)

# dim_date key
ol_with_date = ol_with_date.withColumn(
    "date_key",
    F.date_format(F.col("order_date_eastern"), "yyyyMMdd").cast("int"),
)

# Slice 1 ETL window
ol_filtered = ol_with_date.filter(
    (F.col("order_date_eastern") >= ETL_START) &
    (F.col("order_date_eastern") <= ETL_END)
)

print("[INFO] Shopify order lines filtered to ETL window")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Prepare TW attribution clicks — Last-touch + source normalization
# MAGIC
# MAGIC Actual TW click schema:
# MAGIC - `_triple_whale_order_id`
# MAGIC - `source`
# MAGIC - `click_date`
# MAGIC - `position`
# MAGIC
# MAGIC Join:
# MAGIC - Shopify `order_line.order_id`
# MAGIC - TW `_triple_whale_order_id`
# MAGIC
# MAGIC Last-touch rule:
# MAGIC - `position DESC`
# MAGIC - `click_date DESC`
# MAGIC
# MAGIC Normalization rules:
# MAGIC - trim spaces
# MAGIC - values beginning with `google%` -> `google-ads`
# MAGIC - case-insensitive `emarsys` -> `Emarsys`
# MAGIC - all other values unchanged

# COMMAND ----------

print("[INFO] Preparing TW attribution_order_click ...")

aoc_cols = set(aoc.columns)

required_cols = {
    "_triple_whale_order_id",
    "source",
    "click_date",
    "position",
}

missing_cols = required_cols - aoc_cols

if missing_cols:
    raise AssertionError(
        f"[FAIL] Missing required columns in attribution_order_click: {sorted(missing_cols)}. "
        f"Actual columns: {aoc.columns}"
    )

print("[INFO] TW join field: aoc._triple_whale_order_id -> Shopify ol.order_id")
print("[INFO] TW source field: source")
print("[INFO] TW touch timestamp field: click_date")
print("[INFO] TW last-touch order: position DESC, click_date DESC")

# Last-touch deduplication:
# one TW click attribution row per order.
# Original design: position DESC, then click_date DESC.
tw_dedup_window = Window.partitionBy(
    F.col("aoc._triple_whale_order_id").cast("string")
).orderBy(
    F.col("aoc.position").cast("int").desc_nulls_last(),
    F.col("aoc.click_date").desc_nulls_last(),
)

tw_lasttouch = (
    aoc
    .withColumn("_rn", F.row_number().over(tw_dedup_window))
    .filter(F.col("_rn") == 1)
    .drop("_rn")
    .select(
        F.col("aoc._triple_whale_order_id").cast("string").alias("tw_order_id"),
        F.col("aoc.source").alias("tw_channel_source"),
        F.col("aoc.click_date").alias("tw_touch_ts"),
        F.col("aoc.position").cast("int").alias("position"),
        F.col("aoc.attribution_model"),
        F.col("aoc.campaign_id"),
        F.col("aoc.adset_id"),
        F.col("aoc.ad_id"),
    )
)

# Source value normalization.
tw_lasttouch_norm = (
    tw_lasttouch
    .withColumn("src_t", F.trim(F.col("tw_channel_source")))
    .withColumn(
        "channel_source_norm",
        F.when(F.col("src_t").rlike("(?i)^google%"), F.lit("google-ads"))
         .when(F.lower(F.col("src_t")) == F.lit("emarsys"), F.lit("Emarsys"))
         .otherwise(F.col("src_t"))
    )
    .drop("src_t")
)

print("[INFO] TW last-touch attribution prepared with normalized source")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Join TW attribution onto Shopify order lines

# COMMAND ----------

print("[INFO] Joining TW attribution onto order lines ...")

ol_tw = ol_filtered.join(
    tw_lasttouch_norm,
    on=F.col("ol.order_id").cast("string") == F.col("tw_order_id"),
    how="left",
)

# One action only for TW join diagnostics.
tw_join_stats = ol_tw.agg(
    F.count("*").alias("total_tw"),
    F.sum(F.when(F.col("tw_order_id").isNotNull(), 1).otherwise(0)).alias("matched_tw"),
    F.sum(F.when(F.col("tw_order_id").isNull(), 1).otherwise(0)).alias("unmatched_tw"),
).first()

total_tw = tw_join_stats["total_tw"]
matched_tw = tw_join_stats["matched_tw"]
unmatched_tw = tw_join_stats["unmatched_tw"]

pct_unmatched = unmatched_tw / total_tw if total_tw > 0 else 0

print(
    f"[INFO] TW join — matched: {matched_tw:,} | unmatched: {unmatched_tw:,} "
    f"| unmatched%: {pct_unmatched:.3%}"
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6. Join conformed dimensions

# COMMAND ----------

print("[INFO] Joining dim_date ...")

ol_d = ol_tw.join(
    dim_date.select(
        F.col("dd.date_key"),
        F.col("dd.iso_year"),
        F.col("dd.iso_week"),
    ),
    on="date_key",
    how="left",
)

print("[INFO] Joining dim_product ...")

ol_dp = ol_d.join(
    dim_product.select(
        F.col("dp.product_key"),
        F.col("dp.sku").alias("dp_sku"),
        F.col("dp.vend_id"),
    ),
    on=F.col("ol.sku") == F.col("dp_sku"),
    how="left",
)

print("[INFO] Joining dim_channel ...")

# IMPORTANT:
# Join normalized TW source, not raw TW source.
ol_dc = ol_dp.join(
    dim_channel.select(
        F.col("dc.channel_key"),
        F.col("dc.channel_source").alias("dc_channel_source"),
    ),
    on=F.col("channel_source_norm") == F.col("dc_channel_source"),
    how="left",
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 7. Build fact_raw and cache
# MAGIC
# MAGIC Classic compute supports cache.
# MAGIC We cache and materialize `fact_raw` once so DQ and write can reuse it
# MAGIC instead of recomputing the full Shopify + TW + dim join lineage.

# COMMAND ----------

print("[INFO] Building fact_raw ...")

fact_raw = (
    ol_dc.select(
        # Surrogate keys
        F.coalesce(F.col("dc.channel_key"), F.lit(0)).alias("channel_key"),
        F.col("dp.product_key"),
        F.col("date_key"),

        # Degenerate dimensions
        F.col("ol.order_id").cast("string").alias("shopify_order_id"),
        F.col("shopify_order_name"),
        F.col("tw_order_id"),
        F.col("ol.id").cast("string").alias("shopify_line_id"),
        F.col("ol.sku").alias("sku_raw"),

        # Facts
        F.col("ol.quantity").cast("int").alias("quantity"),
        F.col("ol.price").cast("decimal(10,2)").alias("pre_tax_price"),

        # Attribution metadata
        F.col("tw_channel_source"),
        F.col("channel_source_norm"),
        F.col("tw_touch_ts"),
        F.col("attribution_model"),
        F.col("position"),
        F.col("campaign_id"),
        F.col("adset_id"),
        F.col("ad_id"),

        # Flags
        F.col("financial_status"),
        F.when(F.col("financial_status") == "refunded", True)
         .otherwise(False).alias("is_refunded"),

        # ISO date fields
        F.col("dd.iso_year"),
        F.col("dd.iso_week"),

        # Lineage
        F.current_timestamp().alias("_ingested_at"),
    )
    .cache()
)

# Force materialization once.
# After this, DQ and write should reuse cached fact_raw.
materialized_count = fact_raw.count()

print(f"[INFO] fact_raw built and cached: {materialized_count:,} rows")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 8. Multi-tier DQ SLO check — single aggregation

# COMMAND ----------

print("[INFO] Running DQ checks in a single aggregation ...")

dq_stats = fact_raw.agg(
    F.count("*").alias("total"),
    F.sum(F.when(F.col("channel_key") == 0, 1).otherwise(0)).alias("channel_unknown"),
    F.sum(F.when(F.col("product_key").isNull(), 1).otherwise(0)).alias("product_null"),
).first()

total = dq_stats["total"]
channel_unknown = dq_stats["channel_unknown"]
product_null = dq_stats["product_null"]

channel_unknown_pct = channel_unknown / total if total > 0 else 0
product_null_pct = product_null / total if total > 0 else 0

print(f"[INFO] Total fact rows before write: {total:,}")
print(f"[INFO] channel DQ — unknown: {channel_unknown:,} ({channel_unknown_pct:.3%})")
print(f"[INFO] product DQ — unmatched: {product_null:,} ({product_null_pct:.3%})")

# --- Channel DQ ---
if channel_unknown_pct >= DQ_CHANNEL_FAIL_PCT:
    print("[INFO] Top unknown channel source values:")

    fact_raw.filter(F.col("channel_key") == 0) \
        .groupBy("tw_channel_source", "channel_source_norm") \
        .count() \
        .orderBy(F.desc("count")) \
        .show(30, truncate=False)

    raise AssertionError(
        f"[FAIL] Channel match rate below SLO: {channel_unknown_pct:.3%} unmatched "
        f"(threshold: {DQ_CHANNEL_FAIL_PCT:.1%}). "
        f"Check dim_channel seed and TW source values."
    )

elif channel_unknown_pct >= DQ_CHANNEL_WARN_PCT:
    print(
        f"[WARN] Channel unmatched rate {channel_unknown_pct:.3%} exceeds WARN "
        f"threshold {DQ_CHANNEL_WARN_PCT:.1%} — investigate but pipeline continues."
    )

else:
    print(
        f"[PASS] Channel DQ — {channel_unknown_pct:.3%} unmatched "
        f"below WARN threshold"
    )

# --- Product DQ ---
if product_null_pct >= DQ_PRODUCT_FAIL_PCT:
    print("[INFO] Top unmatched product SKU values:")

    fact_raw.filter(F.col("product_key").isNull()) \
        .groupBy("sku_raw") \
        .count() \
        .orderBy(F.desc("count")) \
        .show(30, truncate=False)

    raise AssertionError(
        f"[FAIL] Product match rate below SLO: {product_null_pct:.3%} unmatched "
        f"(threshold: {DQ_PRODUCT_FAIL_PCT:.1%}). "
        f"Check dim_product SKU coverage vs Shopify order_line.sku."
    )

elif product_null_pct >= DQ_PRODUCT_WARN_PCT:
    print(
        f"[WARN] Product unmatched rate {product_null_pct:.3%} exceeds WARN "
        f"threshold {DQ_PRODUCT_WARN_PCT:.1%} — investigate but pipeline continues."
    )

else:
    print(
        f"[PASS] Product DQ — {product_null_pct:.3%} unmatched "
        f"below WARN threshold"
    )

# COMMAND ----------

# MAGIC %md
# MAGIC ## 9. Write Delta table
# MAGIC
# MAGIC Write cached `fact_raw` to Delta.
# MAGIC
# MAGIC `NUM_WRITE_PARTITIONS = 32` is chosen for small Personal Compute.
# MAGIC This avoids excessive small files and task scheduling overhead.

# COMMAND ----------

print(f"[INFO] Writing to {FULL_TARGET} ...")

fact_to_write = fact_raw.repartition(NUM_WRITE_PARTITIONS)

(
    fact_to_write.write
        .format("delta")
        .mode("overwrite")
        .option("overwriteSchema", "true")
        .partitionBy("iso_year", "iso_week")
        .saveAsTable(FULL_TARGET)
)

print("[OK] Write complete")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 10. Optional post-write validation

# COMMAND ----------

if RUN_POST_WRITE_VALIDATION:
    print("[INFO] Running post-write validation ...")

    written = spark.table(FULL_TARGET)

    written.select(
        F.count("*").alias("row_count"),
        F.min("date_key").alias("min_date"),
        F.max("date_key").alias("max_date"),
    ).show()

    print("[INFO] Latest Delta history:")
    spark.sql(f"DESCRIBE HISTORY {FULL_TARGET}").show(5, truncate=False)

else:
    print("[INFO] Skipping post-write full-table validation to avoid extra scan.")
    print("[INFO] Latest Delta history:")
    spark.sql(f"DESCRIBE HISTORY {FULL_TARGET}").show(5, truncate=False)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 11. Cleanup

# COMMAND ----------

print("[INFO] Releasing cached fact_raw ...")
fact_raw.unpersist()

print(f"\n[OK] fact_orders_line full rebuild completed — {total:,} rows prepared and written")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 12. Summary Notes
# MAGIC
# MAGIC | Metric | Value |
# MAGIC |---|---|
# MAGIC | Target table | `mvdevdatabricks.analytics_platform_32degrees.fact_orders_line` |
# MAGIC | ETL window | 2025-07-01 → present |
# MAGIC | Grain | One row per Shopify order line |
# MAGIC | TW source table | `attribution_order_click` |
# MAGIC | TW join | Shopify `order_line.order_id` → TW `_triple_whale_order_id` |
# MAGIC | TW attribution | Last-touch dedup via `position DESC`, `click_date DESC` |
# MAGIC | Channel normalization | `emarsys` → `Emarsys`; `google%...` → `google-ads`; others unchanged |
# MAGIC | Channel fallback | `channel_key = 0` for unmatched channel values |
# MAGIC | DQ SLO | Multi-tier PASS/WARN/FAIL |
# MAGIC | Performance | Cached `fact_raw`, single TW stats aggregation, single DQ aggregation, 32 write partitions |
# MAGIC | Compute | Classic / Personal Compute |
# MAGIC | Timezone | DST-aware `America/New_York` |
# MAGIC | Partition | `iso_year`, `iso_week` |
# MAGIC | Write mode | Full overwrite |