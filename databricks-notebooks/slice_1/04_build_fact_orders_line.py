# Databricks notebook source
# MAGIC %md
# MAGIC # Slice 1 — Notebook 04: Build `fact_orders_line`
# MAGIC # Classic Compute Full Rebuild Version
# MAGIC
# MAGIC **Purpose**: Join Shopify order lines with Triple Whale click attribution
# MAGIC and conformed dimensions to produce the row-grain sales fact table for Slice 1.
# MAGIC
# MAGIC **Run mode**: INCREMENTAL (default) or FULL REBUILD / BACKFILL.
# MAGIC Controlled by the `FORCE_FULL_REFRESH` flag in section 1.
# MAGIC - `FORCE_FULL_REFRESH = True`  -> rebuild entire history, overwrite, reset watermark.
# MAGIC - `FORCE_FULL_REFRESH = False` -> incremental MERGE upsert by `shopify_line_id`,
# MAGIC   reading only orders changed since (watermark - 2-day lookback).
# MAGIC Watermark column: Shopify `order.updated_at` (bumped on refunds/edits, so
# MAGIC late-arriving refunds are re-captured). Watermark state table:
# MAGIC `analytics_platform.pipeline_watermark`. See Decision 28.
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
# MAGIC - Pre-filters TW to the current batch's order ids BEFORE the last-touch
# MAGIC   window (v4 — see changelog), so the window does not scan the whole TW table.
# MAGIC - Adds conservative source normalization before `dim_channel` join.
# MAGIC - Combines TW join diagnostics into one aggregation.
# MAGIC - Combines DQ metrics into one aggregation.
# MAGIC - Caches `fact_raw` (both modes after v4) before DQ and write.
# MAGIC - Uses `NUM_WRITE_PARTITIONS = 32`, suitable for small Personal Compute.
# MAGIC
# MAGIC **Cutover (2026-06) — Shopify source moved Fivetran -> dpsync**
# MAGIC - `SHOPIFY_CATALOG = "dpsync"` (was `"analytics_catalog"` / Fivetran).
# MAGIC - order / order_line / order_line_refund and order_metafield now ALL come
# MAGIC   from dpsync, so id types are consistent across the joins.
# MAGIC - Run a FULL_REFRESH on cutover, then reconcile against the last validated
# MAGIC   baseline (-1.51%) before pointing the daily job at this version.
# MAGIC
# MAGIC **v3 (2026-05-27) — corrected exclusion model (Decision 22 v3)**
# MAGIC - is_sales_attributable = NOT (is_exc_order OR is_replacement_order).
# MAGIC   Refund is NO LONGER an order-level exclusion — order-level refund
# MAGIC   exclusion was disproven by Day-5 reconciliation (residual 1.97%->6.57%).
# MAGIC - Adds `refunded_quantity` — line-level SUM(order_line_refund.quantity)
# MAGIC   over ALL restock types (return / no_restock / cancel). Net units =
# MAGIC   quantity - refunded_quantity.
# MAGIC - Drops `is_refunded` and `is_refund_order` (rejected order-level model).
# MAGIC - is_replacement_order: from dpsync `order_metafield.replace_refund == 'Replace'`;
# MAGIC   graceful degradation to FALSE if the table is unavailable.
# MAGIC
# MAGIC **v4 (2026-06-17) — single-node OOM fix (supersedes Decision 60)**
# MAGIC - Root cause: the section-4 last-touch window (`row_number()` partitioned by
# MAGIC   order id) is a FULL shuffle+sort of the ENTIRE `attribution_order_click`
# MAGIC   table — it does NOT shrink in incremental mode and grows daily, so the
# MAGIC   driver OOM crept in as TW history accumulated. Decision 60's
# MAGIC   "no-cache-on-incremental" made it worse: the heavy join lineage was then
# MAGIC   recomputed by every downstream action (DQ agg, exclusion breakdown,
# MAGIC   max-watermark, MERGE).
# MAGIC - Fix: pre-filter TW to ONLY this batch's order ids (left-semi join) BEFORE
# MAGIC   the window, so the window input collapses to the changed orders in
# MAGIC   incremental mode. Lossless — those TW rows are dropped by the section-5
# MAGIC   left-join anyway. Full builds span all orders as before. No forced
# MAGIC   broadcast — AQE picks the join strategy so a large batch can't OOM.
# MAGIC - With fact_raw now small in incremental mode, cache is restored in BOTH
# MAGIC   modes (cheap + stops recompute). Section-11 unpersist made unconditional
# MAGIC   (also fixes a `FORCE_FULL_REFRESH` typo that leaked the cache on incremental).

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Configuration

# COMMAND ----------
FORCE_FULL_REFRESH = False
from pyspark.sql import functions as F
from pyspark.sql.window import Window

# --- Source tables ---
# CUTOVER (2026-06): Shopify tables now read from dpsync (Fivetran -> dpsync
# migration complete, per Cal). Previously SHOPIFY_CATALOG = "analytics_catalog".
SHOPIFY_CATALOG = "dpsync"
SHOPIFY_SCHEMA = "shopify_raw"

TW_CATALOG = "federated_catalog"
TW_SCHEMA = "triple_whale"
TW_ATTRIBUTION_CLICK_TABLE = "attribution_order_click"

# --- Target ---
TARGET_CATALOG = "analytics_catalog"
TARGET_SCHEMA = "analytics_platform"
TARGET_TABLE = "fact_orders_line"
FULL_TARGET = f"{TARGET_CATALOG}.{TARGET_SCHEMA}.{TARGET_TABLE}"

# --- Dims ---
DIM_DATE = f"{TARGET_CATALOG}.{TARGET_SCHEMA}.dim_date"
DIM_PRODUCT = f"{TARGET_CATALOG}.{TARGET_SCHEMA}.dim_product"
DIM_CHANNEL = f"{TARGET_CATALOG}.{TARGET_SCHEMA}.dim_channel"

# --- ETL window (full-refresh lower bound) ---
ETL_START = "2025-07-01"
ETL_END = "2099-12-31"

# =====================================================================
# INCREMENTAL CONTROL (Decision 28)
# =====================================================================
# FULL_REFRESH = True  -> rebuild all history (overwrite), reset watermark.
#                         Use for: first build, schema change, recovery, CUTOVER.
# FULL_REFRESH = False -> incremental MERGE upsert (daily default).
#
# Override at runtime from a Workflows task parameter:
#   dbutils.widgets.text("full_refresh", "false")
FULL_REFRESH = FORCE_FULL_REFRESH

# Watermark state table — one row, tracks last successfully-loaded updated_at.
WATERMARK_TABLE = f"{TARGET_CATALOG}.{TARGET_SCHEMA}.pipeline_watermark"
WATERMARK_KEY = TARGET_TABLE          # "fact_orders_line"
LOOKBACK_DAYS = 2                     # re-scan 2 days back to catch late arrivals

# Grain key for MERGE upsert (one row per Shopify order line).
MERGE_KEY = "shopify_line_id"

print(f"[INFO] Run mode: {'FULL_REFRESH' if FULL_REFRESH else 'INCREMENTAL'}")

# Ensure the watermark table exists (no-op if already there).
spark.sql(f"""
    CREATE TABLE IF NOT EXISTS {WATERMARK_TABLE} (
        table_name      STRING,
        last_watermark  TIMESTAMP,
        updated_at      TIMESTAMP
    ) USING DELTA
""")

# Read the current watermark for this table (None if first ever run).
def _read_watermark():
    rows = (
        spark.table(WATERMARK_TABLE)
        .filter(F.col("table_name") == F.lit(WATERMARK_KEY))
        .select("last_watermark")
        .collect()
    )
    return rows[0]["last_watermark"] if rows else None

_current_wm = _read_watermark()

# Compute the incremental lower bound on order.updated_at.
# Full refresh OR no prior watermark -> go back to the beginning of history.
if FULL_REFRESH or _current_wm is None:
    INCR_FROM = None  # signals "no updated_at filter" downstream
    if not FULL_REFRESH and _current_wm is None:
        print("[WARN] No watermark found — first incremental run behaves as full build.")
else:
    from datetime import timedelta
    INCR_FROM = _current_wm - timedelta(days=LOOKBACK_DAYS)
    print(f"[INFO] Incremental lower bound (updated_at >= ): {INCR_FROM} "
          f"(watermark {_current_wm} minus {LOOKBACK_DAYS}d lookback)")

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
print(f"[INFO] Shopify source catalog: {SHOPIFY_CATALOG} (dpsync after cutover)")
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

# Shopify line-level refund detail — one row per refunded order line.
# Used in section 3c to build refunded_quantity (line-level net deduction).
# REPLACES the previous `refund` parent-table load: refunds are now netted at
# line grain, NOT excluded at order grain (Decision 22 v3).
order_line_refund = spark.table(
    f"{SHOPIFY_CATALOG}.{SHOPIFY_SCHEMA}.order_line_refund"
).alias("olr")

aoc = spark.table(f"{TW_CATALOG}.{TW_SCHEMA}.{TW_ATTRIBUTION_CLICK_TABLE}").alias("aoc")

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

# Verify the watermark column exists on the Shopify order table.
if "updated_at" not in [c.lower() for c in orders.columns]:
    raise ValueError(
        "Shopify 'order' table has no 'updated_at' column — cannot run "
        f"incremental. Available columns: {orders.columns}"
    )

# INCREMENTAL: restrict orders to those changed since the lookback bound.
# updated_at is bumped by refunds/edits, so this re-captures late refunds.
orders_scoped = orders
if INCR_FROM is not None:
    orders_scoped = orders.filter(F.col("o.updated_at") >= F.lit(INCR_FROM))
    print(f"[INFO] INCREMENTAL: orders filtered to updated_at >= {INCR_FROM}")
else:
    print("[INFO] FULL scan of orders (no updated_at filter)")

ol_with_date = order_lines.join(
    orders_scoped.select(
        F.col("o.id").alias("order_id_hdr"),
        F.col("o.name").alias("shopify_order_name"),
        F.col("o.processed_at").alias("processed_at"),
        F.col("o.financial_status").alias("financial_status"),
        F.col("o.updated_at").alias("order_updated_at"),
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
# MAGIC ## 3b. Order-level exclusion flags — `is_sales_attributable` (Decision 22 v3)
# MAGIC
# MAGIC Materializes the "should this row count as channel-attributable sales?"
# MAGIC business rule once at the data layer, instead of re-filtering replacement /
# MAGIC EXC orders in every downstream query.
# MAGIC
# MAGIC Whole-order exclusion signals (EXC + replacement). Refund is handled
# MAGIC separately at LINE grain in section 3c (Decision 22 v3):
# MAGIC
# MAGIC | Flag | Signal | Status |
# MAGIC |---|---|---|
# MAGIC | `is_exc_order` | `order.name` contains `EXC` | Native, ready |
# MAGIC | `is_replacement_order` | dpsync `order_metafield.replace_refund` == `Replace` | Live (dpsync) |
# MAGIC
# MAGIC `is_sales_attributable` = NOT (exc OR replacement). Refund is NOT a
# MAGIC whole-order exclusion — it is netted at LINE grain in section 3c via
# MAGIC `refunded_quantity` (order-level refund exclusion was disproven by Day-5
# MAGIC reconciliation: residual worsened 1.97% -> 6.57%).
# MAGIC
# MAGIC Flags are computed AFTER the ETL-window filter (operate on ~10M rows, not 44M).

# COMMAND ----------

print("[INFO] Building order-level exclusion flags ...")

# ---------------------------------------------------------------------------
# Decision 22 v3 — corrected exclusion model
# ---------------------------------------------------------------------------
# is_sales_attributable handles ONLY whole-order exclusions: EXC + replacement.
# Refunds are NOT a whole-order exclusion — a refunded order usually still has
# genuinely-sold lines. Refunds are netted at LINE grain in section 3c via
# refunded_quantity. (Order-level refund exclusion was disproven by Day-5
# reconciliation: residual worsened 1.97% -> 6.57%.)
# ---------------------------------------------------------------------------

# --- EXC: order name contains 'EXC' (case-sensitive). coalesce guards NULL names.
ol_flagged = ol_filtered.withColumn(
    "is_exc_order",
    F.coalesce(F.col("shopify_order_name").like("%EXC%"), F.lit(False)),
)

# --- replacement: from the dpsync order_metafield table --------------------
# dpsync stores Shopify order metafields as a WIDE table (one row per order),
# not Fivetran's EAV key/value/owner_id shape. A replacement order has
# replace_refund == 'Replace' (dpsync flattens Shopify's '["Replace"]' to the
# plain string 'Replace'). We take the distinct order_ids and left-join to flag
# is_replacement_order. order_id is cast to string on BOTH sides so the join is
# type-safe regardless of how each table types the id. If the table is missing,
# degrade to FALSE (no crash; replacements simply not excluded that run).
ORDER_METAFIELD_TABLE = "dpsync.shopify_raw.order_metafield"
REPLACEMENT_COL = "replace_refund"
REPLACEMENT_VALUE = "Replace"

def _table_exists(fq_name: str) -> bool:
    try:
        spark.read.table(fq_name).limit(0).count()
        return True
    except Exception:
        return False

_has_mf_table = _table_exists(ORDER_METAFIELD_TABLE)

if _has_mf_table:
    order_mf = spark.table(ORDER_METAFIELD_TABLE)
    print(f"[INFO] order_metafield table detected. Columns: {order_mf.columns}")

    repl_order_ids = (
        order_mf
        .filter(F.col(REPLACEMENT_COL) == F.lit(REPLACEMENT_VALUE))
        .select(F.col("order_id").cast("string").alias("_repl_order_id"))
        .distinct()
    )
    ol_flagged = (
        ol_flagged
        .join(
            F.broadcast(repl_order_ids),
            on=F.col("order_id_hdr").cast("string") == F.col("_repl_order_id"),
            how="left",
        )
        .withColumn("is_replacement_order", F.col("_repl_order_id").isNotNull())
        .drop("_repl_order_id")
    )
    print(f"[INFO] is_replacement_order from {ORDER_METAFIELD_TABLE} "
          f"({REPLACEMENT_COL} == '{REPLACEMENT_VALUE}')")
else:
    ol_flagged = ol_flagged.withColumn("is_replacement_order", F.lit(False))
    print(f"[WARN] {ORDER_METAFIELD_TABLE} NOT available — "
          f"is_replacement_order defaults to FALSE")

# --- union rule ------------------------------------------------------------
ol_flagged = ol_flagged.withColumn(
    "is_sales_attributable",
    ~(F.col("is_exc_order") | F.col("is_replacement_order")),
)

print("[INFO] Exclusion flags built: is_exc_order, is_replacement_order, "
      "is_sales_attributable")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3c. Line-level refund netting — `refunded_quantity` (Decision 22 v3)
# MAGIC
# MAGIC Refunds netted at order-line grain, not excluded at order grain.
# MAGIC `refunded_quantity` = SUM of `order_line_refund.quantity` for the line,
# MAGIC across ALL `restock_type` values (return / no_restock / cancel /
# MAGIC legacy_restock). Net units = `quantity - refunded_quantity`.
# MAGIC `restock_type='cancel'` IS included — a cancelled unit is not a sale,
# MAGIC and line-level netting handles full and partial cancellations correctly.

# COMMAND ----------

print("[INFO] Building line-level refunded_quantity ...")

# One row per refunded order_line. A line can have multiple refund rows
# (partial refunds, or refund + cancel), so aggregate first.
refund_by_line = (
    order_line_refund
    .where(F.col("olr.order_line_id").isNotNull())
    .groupBy(F.col("olr.order_line_id").alias("_refund_line_id"))
    .agg(F.sum(F.col("olr.quantity")).alias("_refunded_qty"))
)

# Left-join onto the flagged order lines; lines with no refund -> 0.
# If F.broadcast OOMs on small Personal Compute, drop it and let AQE decide.
ol_flagged = (
    ol_flagged
    .join(F.broadcast(refund_by_line),
          on=F.col("ol.id") == F.col("_refund_line_id"), how="left")
    .withColumn(
        "refunded_quantity",
        F.coalesce(F.round(F.col("_refunded_qty")), F.lit(0)).cast("int"),
    )
    .drop("_refund_line_id", "_refunded_qty")
)

print("[INFO] refunded_quantity built (all restock types netted at line grain)")

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
# MAGIC
# MAGIC **v4 perf (2026-06-17)**: the last-touch window below is a FULL shuffle+sort
# MAGIC of the ENTIRE `attribution_order_click` table (partitioned by order id) — it
# MAGIC does NOT shrink in incremental mode and grows daily, which is the dominant
# MAGIC single-node OOM driver. In incremental mode we pre-filter TW to ONLY this
# MAGIC batch's order ids (left-semi join) BEFORE the window. Lossless: those TW rows
# MAGIC would be dropped by the section-5 left-join anyway. Full builds span all
# MAGIC orders. No forced broadcast — AQE chooses the join strategy.
# MAGIC
# MAGIC **Ordering note**: this section now depends on `ol_flagged` (section 3c), so
# MAGIC it MUST run after 3 / 3b / 3c (the notebook's existing top-to-bottom order).

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

# ---------------------------------------------------------------------------
# v4 PERF FIX (supersedes Decision 60's no-cache approach)
# ---------------------------------------------------------------------------
# Pre-filter TW to ONLY the orders present in THIS batch BEFORE the last-touch
# window. The window is a full shuffle+sort of the whole TW table and does not
# shrink with incremental mode; on single-node compute that is what OOMs.
# Lossless: any TW row whose order is not in the batch would be dropped by the
# section-5 left-join anyway. Incremental collapses the window input from
# millions of rows to just the changed orders. Full build keeps all orders
# (window spans everything regardless). No explicit broadcast — let AQE pick the
# join strategy so a large batch (e.g. an upstream bulk op) can't OOM a forced
# broadcast.
# ---------------------------------------------------------------------------
if FULL_REFRESH or INCR_FROM is None:
    aoc_scoped = aoc
    print("[INFO] TW window spans FULL attribution table (full build / no watermark).")
else:
    _batch_order_ids = (
        ol_flagged
        .select(F.col("ol.order_id").cast("string").alias("_batch_oid"))
        .distinct()
    )
    aoc_scoped = (
        aoc.join(
            _batch_order_ids,
            on=F.col("aoc._triple_whale_order_id").cast("string") == F.col("_batch_oid"),
            how="left_semi",
        )
        .alias("aoc")  # re-establish alias for the window/select column refs below
    )
    print("[INFO] TW pre-filtered to this batch's order ids before the last-touch window.")

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
    aoc_scoped
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

# NOTE: input is ol_flagged (carries the section 3b exclusion flags), not ol_filtered.
ol_tw = ol_flagged.join(
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
# MAGIC
# MAGIC **v4 (2026-06-17)**: cache in BOTH modes (supersedes Decision 60). With the
# MAGIC section-4 TW pre-filter, incremental `fact_raw` is now small, so caching is
# MAGIC cheap AND it stops the heavy join lineage (especially the TW window) from
# MAGIC being recomputed by the 4-5 downstream actions (DQ agg, exclusion breakdown,
# MAGIC max-watermark, MERGE).

# COMMAND ----------

print("[INFO] Building fact_raw ...")

fact_raw = (
    ol_dc.select(
        # Surrogate keys
        F.coalesce(F.col("dc.channel_key"), F.lit(0)).alias("channel_key"),
        F.coalesce(F.col("dp.product_key"), F.lit(0)).alias("product_key"),
        F.col("date_key"),

        # Degenerate dimensions
        F.col("ol.order_id").cast("string").alias("shopify_order_id"),
        F.col("shopify_order_name"),
        F.col("tw_order_id"),
        F.col("ol.id").cast("string").alias("shopify_line_id"),
        F.col("ol.sku").alias("sku_raw"),

        # Measures
        F.col("ol.quantity").cast("int").alias("quantity"),
        F.col("refunded_quantity"),                          # NEW — Decision 22 v3
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

        # Order status + business-rule flags (Decision 22 v3)
        F.col("financial_status"),
        F.col("is_exc_order"),
        F.col("is_replacement_order"),
        F.col("is_sales_attributable"),

        # ISO date fields
        F.col("dd.iso_year"),
        F.col("dd.iso_week"),

        # Lineage + incremental watermark source
        F.col("order_updated_at"),
        F.current_timestamp().alias("_ingested_at"),
    )
)

# v4 PERF FIX (supersedes Decision 60): cache in BOTH modes.
# After the section-4 TW pre-filter, incremental fact_raw is small, so caching
# is cheap AND it prevents the heavy join lineage (esp. the TW window) from being
# recomputed by the downstream DQ agg, exclusion breakdown, max-watermark, MERGE.
fact_raw = fact_raw.cache()
materialized_count = fact_raw.count()
print(f"[INFO] fact_raw cached & materialized: {materialized_count:,} rows "
      f"({'FULL_REFRESH' if FULL_REFRESH else 'INCREMENTAL'})")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 8. Multi-tier DQ SLO check — single aggregation

# COMMAND ----------

print("[INFO] Running DQ checks in a single aggregation ...")

dq_stats = fact_raw.agg(
    F.count("*").alias("total"),
    F.sum(F.when(F.col("channel_key") == 0, 1).otherwise(0)).alias("channel_unknown"),
    F.sum(F.when(F.col("product_key") == 0, 1).otherwise(0)).alias("product_null"),
    F.sum(F.when(~F.col("is_sales_attributable"), 1).otherwise(0)).alias("excluded_rows"),
    F.sum("quantity").alias("gross_units"),
    F.sum("refunded_quantity").alias("refunded_units"),
).first()

total = dq_stats["total"]
channel_unknown = dq_stats["channel_unknown"]
product_null = dq_stats["product_null"]
excluded_rows = dq_stats["excluded_rows"]
gross_units = dq_stats["gross_units"]
refunded_units = dq_stats["refunded_units"]

channel_unknown_pct = channel_unknown / total if total > 0 else 0
product_null_pct = product_null / total if total > 0 else 0
excluded_pct = excluded_rows / total if total > 0 else 0

print(f"[INFO] Total fact rows before write: {total:,}")
print(f"[INFO] channel DQ — unknown: {channel_unknown:,} ({channel_unknown_pct:.3%})")
print(f"[INFO] product DQ — unmatched: {product_null:,} ({product_null_pct:.3%})")

# --- Channel DQ ---
# NOTE: the FAIL threshold is a proportion calibrated on the FULL dataset
# (large denominator). On an INCREMENTAL batch the denominator is only the
# changed orders, so a handful of (legitimately) unmatched rows can inflate the
# percentage past the threshold and cause a false block. Therefore: enforce the
# hard gate on FULL_REFRESH; downgrade to a non-blocking WARN on incremental.
if channel_unknown_pct >= DQ_CHANNEL_FAIL_PCT:
    print("[INFO] Top unknown channel source values:")
    fact_raw.filter(F.col("channel_key") == 0) \
        .groupBy("tw_channel_source", "channel_source_norm") \
        .count().orderBy(F.desc("count")).show(30, truncate=False)
    _channel_msg = (
        f"Channel match rate below SLO: {channel_unknown_pct:.3%} unmatched "
        f"(threshold: {DQ_CHANNEL_FAIL_PCT:.1%}). Check dim_channel seed and TW source values."
    )
    if FULL_REFRESH:
        raise AssertionError(f"[FAIL] {_channel_msg}")
    else:
        print(f"[WARN] {_channel_msg}")
        print("[WARN] Incremental batch has a small denominator, so the unmatched "
              "percentage is inflated; not blocking. Full-refresh runs still enforce this gate.")
elif channel_unknown_pct >= DQ_CHANNEL_WARN_PCT:
    print(f"[WARN] Channel unmatched rate {channel_unknown_pct:.3%} exceeds WARN "
          f"threshold {DQ_CHANNEL_WARN_PCT:.1%} — investigate but pipeline continues.")
else:
    print(f"[PASS] Channel DQ — {channel_unknown_pct:.3%} unmatched below WARN threshold")

# --- Product DQ ---
# Same full-vs-incremental rationale as Channel DQ above.
if product_null_pct >= DQ_PRODUCT_FAIL_PCT:
    print("[INFO] Top unmatched product SKU values:")
    fact_raw.filter(F.col("product_key") == 0) \
        .groupBy("sku_raw").count().orderBy(F.desc("count")).show(30, truncate=False)
    _product_msg = (
        f"Product match rate below SLO: {product_null_pct:.3%} unmatched "
        f"(threshold: {DQ_PRODUCT_FAIL_PCT:.1%}). Check dim_product SKU coverage."
    )
    if FULL_REFRESH:
        raise AssertionError(f"[FAIL] {_product_msg}")
    else:
        print(f"[WARN] {_product_msg}")
        print("[WARN] Incremental batch has a small denominator, so the unmatched "
              "percentage is inflated; not blocking. Full-refresh runs still enforce this gate.")
elif product_null_pct >= DQ_PRODUCT_WARN_PCT:
    print(f"[WARN] Product unmatched rate {product_null_pct:.3%} exceeds WARN "
          f"threshold {DQ_PRODUCT_WARN_PCT:.1%} — investigate but pipeline continues.")
else:
    print(f"[PASS] Product DQ — {product_null_pct:.3%} unmatched below WARN threshold")

# --- Sales-model summary (informational only — not a gate) ---
net_units = gross_units - refunded_units
print(f"[INFO] gross units: {gross_units:,} | refunded units (line-level, all "
      f"restock types): {refunded_units:,} | net units: {net_units:,}")
print(f"[INFO] is_sales_attributable=FALSE rows (EXC + replacement): "
      f"{excluded_rows:,} ({excluded_pct:.3%})")
print("[INFO] Exclusion breakdown by reason:")
fact_raw.groupBy(
    "is_exc_order", "is_replacement_order", "is_sales_attributable"
).count().orderBy(F.desc("count")).show(truncate=False)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 9. Write Delta table
# MAGIC
# MAGIC Write cached `fact_raw` to Delta.
# MAGIC
# MAGIC `NUM_WRITE_PARTITIONS = 32` is chosen for small Personal Compute.
# MAGIC This avoids excessive small files and task scheduling overhead.

# COMMAND ----------

from delta.tables import DeltaTable

# Max updated_at in THIS batch -> the new watermark after a successful load.
_batch_max_wm = fact_raw.select(F.max("order_updated_at").alias("m")).first()["m"]

def _update_watermark(new_wm):
    """Idempotently upsert the watermark for this table."""
    if new_wm is None:
        print("[WARN] Batch had no rows / no max updated_at — watermark unchanged.")
        return
    spark.sql(f"DELETE FROM {WATERMARK_TABLE} WHERE table_name = '{WATERMARK_KEY}'")
    spark.createDataFrame(
        [(WATERMARK_KEY, new_wm)],
        "table_name string, last_watermark timestamp",
    ).withColumn("updated_at", F.current_timestamp()) \
     .write.mode("append").saveAsTable(WATERMARK_TABLE)
    print(f"[INFO] Watermark for {WATERMARK_KEY} set to {new_wm}")

_target_exists = spark.catalog.tableExists(FULL_TARGET)

if FULL_REFRESH or not _target_exists:
    # -------- FULL REFRESH: overwrite entire table + reset watermark --------
    print(f"[INFO] FULL_REFRESH write to {FULL_TARGET} ...")
    fact_to_write = fact_raw.repartition(NUM_WRITE_PARTITIONS)
    (
        fact_to_write.write
            .format("delta")
            .mode("overwrite")
            .option("overwriteSchema", "true")
            .partitionBy("iso_year", "iso_week")
            .saveAsTable(FULL_TARGET)
    )
    print("[OK] Full overwrite complete")
    _update_watermark(_batch_max_wm)

else:
    # -------- INCREMENTAL: MERGE upsert by shopify_line_id --------
    print(f"[INFO] INCREMENTAL MERGE into {FULL_TARGET} on {MERGE_KEY} ...")
    delta_target = DeltaTable.forName(spark, FULL_TARGET)
    (
        delta_target.alias("t")
        .merge(
            fact_raw.alias("s"),
            f"t.{MERGE_KEY} = s.{MERGE_KEY}",
        )
        .whenMatchedUpdateAll()
        .whenNotMatchedInsertAll()
        .execute()
    )
    print("[OK] MERGE complete")
    _update_watermark(_batch_max_wm)

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
# v4: unconditional unpersist. We now cache in both modes (section 7), and
# unpersist is safe even if a frame was never cached. (Previously this guarded
# on FORCE_FULL_REFRESH — a typo that also leaked the cache on incremental runs.)
fact_raw.unpersist()
print(f"\n[OK] fact_orders_line load completed "
      f"({'FULL_REFRESH' if FULL_REFRESH else 'INCREMENTAL'}) — load finished")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 12. Summary Notes
# MAGIC
# MAGIC | Metric | Value |
# MAGIC |---|---|
# MAGIC | Target table | `analytics_catalog.analytics_platform.fact_orders_line` |
# MAGIC | Shopify source | `dpsync.shopify_raw` (Fivetran -> dpsync cutover, 2026-06) |
# MAGIC | ETL window | 2025-07-01 → present |
# MAGIC | Grain | One row per Shopify order line |
# MAGIC | TW source table | `attribution_order_click` |
# MAGIC | TW join | Shopify `order_line.order_id` → TW `_triple_whale_order_id` |
# MAGIC | TW attribution | Last-touch dedup via `position DESC`, `click_date DESC` |
# MAGIC | TW perf (v4) | Pre-filter TW to batch order ids (left-semi) before window; AQE join |
# MAGIC | Channel normalization | `emarsys` → `Emarsys`; `google%...` → `google-ads`; others unchanged |
# MAGIC | Channel fallback | `channel_key = 0` for unmatched channel values |
# MAGIC | Sales exclusion | `is_sales_attributable` = NOT(EXC OR replacement) |
# MAGIC | EXC signal | `order.name LIKE '%EXC%'` (native) |
# MAGIC | Refund | line-level netting via `refunded_quantity` (all restock types) |
# MAGIC | Replacement signal | dpsync `order_metafield.replace_refund == 'Replace'` (live) |
# MAGIC | DQ SLO | Multi-tier PASS/WARN/FAIL (hard gate on full-refresh; WARN-only on incremental) |
# MAGIC | Performance | TW batch pre-filter, cached `fact_raw` (both modes), single TW stats agg, single DQ agg, 32 write partitions |
# MAGIC | Compute | Classic / Personal Compute |
# MAGIC | Timezone | DST-aware `America/New_York` |
# MAGIC | Partition | `iso_year`, `iso_week` |
# MAGIC | Write mode | Full overwrite (full-refresh) / MERGE upsert (incremental) |