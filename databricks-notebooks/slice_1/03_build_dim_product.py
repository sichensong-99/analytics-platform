# Databricks notebook source
# MAGIC %md
# MAGIC # Slice 1 — Notebook 03: Build `dim_product`
# MAGIC
# MAGIC **Purpose**: Build the `dim_product` table by joining Shopify active SKUs to the ERS
# MAGIC product master, with graceful degradation (item_description fallback) for unmatched SKUs.
# MAGIC
# MAGIC **Why this design**:
# MAGIC - SCD1 (Type 1) — overwrite on rebuild (Decision 12 — YAGNI on SCD2).
# MAGIC - Graceful degradation via item_description fallback preserves quantity totals
# MAGIC   (matches legacy Panoply pattern, see `docs/legacy_panoply_etl.md` §2.3 Trick 2).
# MAGIC - Reserved sentinel rows: `product_key = -1` for "unknown product" (seeded here).
# MAGIC - **Dual-schema ERS ingest**: supports both the legacy ERS column layout
# MAGIC   (e.g. `Unique_Identifier`, `Vend_ID`, `Item_Description`) and the post-2026
# MAGIC   redesigned layout (e.g. `SKU`, `Style#`, `Item Description`). Detects which
# MAGIC   version is present and normalizes to a single canonical schema.
# MAGIC
# MAGIC **Inputs**:
# MAGIC - ERS master: `/Volumes/mvdevdatabricks/analytics_platform_32degrees/raw_uploads/ers_product_master_<YYYYMMDD>.csv` (latest by filename)
# MAGIC - Shopify: `mvdevdatabricks.shopify_32degrees.order_line` (for active SKU set)
# MAGIC
# MAGIC **Output**: `mvdevdatabricks.analytics_platform_32degrees.dim_product`
# MAGIC
# MAGIC **Idempotent**: Yes — full rebuild via `mode("overwrite")`.
# MAGIC
# MAGIC **Author**: Sia Song
# MAGIC **Created**: 2026-05-19

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Configuration

# COMMAND ----------

import re
from pyspark.sql import DataFrame
from pyspark.sql import functions as F, Window

# ----- Target -----
TARGET_CATALOG = "mvdevdatabricks"
TARGET_SCHEMA = "analytics_platform_32degrees"
TARGET_TABLE = "dim_product"
FULL_TARGET = f"{TARGET_CATALOG}.{TARGET_SCHEMA}.{TARGET_TABLE}"

# ----- Sources -----
SHOPIFY_ORDER_LINE = "mvdevdatabricks.shopify_32degrees.order_line"
SHOPIFY_ORDER = "mvdevdatabricks.shopify_32degrees.order"
ERS_VOLUME_DIR = f"/Volumes/{TARGET_CATALOG}/{TARGET_SCHEMA}/raw_uploads"

# ----- Slice 1 ETL window -----
SLICE_1_START_DATE = "2025-07-01"

# ----- Surrogate key offset -----
# Reserve 0-999 for special / sentinel values (e.g., -1 unknown).
# Real product keys start from 1000+.
SURROGATE_KEY_OFFSET = 1000

# ----- Coverage threshold for DQ -----
MIN_COVERAGE_PCT = 0.99  # ≥ 99% of active SKUs must resolve to a real product key

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. ERS schema detection and normalization
# MAGIC
# MAGIC ERS exists in two known column layouts:
# MAGIC
# MAGIC | Canonical name (internal) | Legacy ERS column | Current ERS column |
# MAGIC |---|---|---|
# MAGIC | `sku` | `Unique_Identifier` | `SKU` |
# MAGIC | `vend_id` | `Vend_ID` | `Style#` |
# MAGIC | `item_description` | `Item_Description` | `Item Description` |
# MAGIC | `season` | `Season` | `Season` |
# MAGIC | `group_name` | `Group` | `Group` |
# MAGIC | `gender` | `Gender` | `Gender` |
# MAGIC | `class_name` | `Class` | `Class` |
# MAGIC | `upc` (optional) | `Item_No` | `UPC` |
# MAGIC | `master_style` (optional) | `Master_style` | `Master Style` |
# MAGIC | `sku_status` (optional) | `SKU_Status` | `SKU Status` |
# MAGIC
# MAGIC The 7 columns above the optional line are required for slice 1. Optional columns
# MAGIC are preserved when present (for slices 3+). Detection is by presence of
# MAGIC `Unique_Identifier` (legacy) or `SKU` (current).

# COMMAND ----------

def detect_and_normalize_ers(df: DataFrame) -> tuple[DataFrame, str]:
    """
    Detect ERS source schema version and normalize column names to canonical internal names.

    Returns:
        Tuple of (normalized DataFrame, detected version label).
    Raises:
        ValueError if neither known schema can be detected.
    """
    cols = df.columns

    # Build legacy and current rename maps. Only columns present in `cols` are renamed.
    LEGACY_MAP = {
        "Unique_Identifier": "sku",
        "Vend_ID": "vend_id",
        "Item_Description": "item_description",
        "Season": "season",
        "Group": "group_name",
        "Gender": "gender",
        "Class": "class_name",
        "Item_No": "upc",
        "Master_style": "master_style",
        "SKU_Status": "sku_status",
        "Color": "color",
        "Size": "size",
        "Cost": "cost",
    }
    CURRENT_MAP = {
        "SKU": "sku",
        "Style#": "vend_id",
        "Item Description": "item_description",
        "Season": "season",
        "Group": "group_name",
        "Gender": "gender",
        "Class": "class_name",
        "UPC": "upc",
        "Master Style": "master_style",
        "SKU Status": "sku_status",
        "Color": "color",
        "Size": "size",
        "Cost": "cost",
        "Retail": "retail",
        "Casepack": "casepack",
        "Style-Color": "style_color",
    }

    # Detect version by presence of disambiguating column
    if "Unique_Identifier" in cols:
        version = "legacy"
        rename_map = LEGACY_MAP
    elif "SKU" in cols:
        version = "current"
        rename_map = CURRENT_MAP
    else:
        raise ValueError(
            f"Unrecognized ERS schema. Neither 'Unique_Identifier' (legacy) nor "
            f"'SKU' (current) found in columns. Got: {cols}"
        )

    print(f"[INFO] Detected ERS schema version: {version}")

    # Apply renames for columns that exist in source
    out = df
    renames_applied = []
    for src_col, dst_col in rename_map.items():
        if src_col in out.columns:
            # Use backticks to handle special characters like '#' and spaces
            out = out.withColumnRenamed(src_col, dst_col)
            renames_applied.append(f"{src_col} -> {dst_col}")

    print(f"[INFO] Renames applied: {len(renames_applied)}")
    for r in renames_applied:
        print(f"        {r}")

    # Verify all slice 1 required columns are present after normalization
    REQUIRED_COLS = ["sku", "vend_id", "item_description", "season",
                     "group_name", "gender", "class_name"]
    missing = [c for c in REQUIRED_COLS if c not in out.columns]
    if missing:
        raise ValueError(
            f"After normalization, missing required columns: {missing}. "
            f"Available columns: {out.columns}"
        )

    return out, version

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Locate latest ERS master file

# COMMAND ----------

# List files in the Volume directory, pick the one with max YYYYMMDD in filename
files = dbutils.fs.ls(ERS_VOLUME_DIR)
ers_pattern = re.compile(r"ers_product_master_(\d{8})\.csv$")

candidates = []
for f in files:
    m = ers_pattern.search(f.name)
    if m:
        candidates.append((m.group(1), f.path))

assert len(candidates) > 0, (
    f"No ers_product_master_YYYYMMDD.csv found in {ERS_VOLUME_DIR}. "
    f"Upload the latest ERS master before running this notebook."
)

candidates.sort(key=lambda x: x[0], reverse=True)
ers_date, ers_path = candidates[0]
print(f"[INFO] Latest ERS master: {ers_path} (date suffix: {ers_date})")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Load ERS product master and normalize schema

# COMMAND ----------

ers_raw = (
    spark.read
         .option("header", "true")
         .option("inferSchema", "true")
         .csv(ers_path)
)

print(f"[INFO] ERS raw row count: {ers_raw.count():,}")
print(f"[INFO] ERS raw columns: {ers_raw.columns}")

# Detect and normalize to canonical column names
ers_normalized, ers_version = detect_and_normalize_ers(ers_raw)

# Project to slice-1-relevant columns + dedupe on sku
SLICE_1_COLS = ["sku", "vend_id", "item_description", "season",
                "group_name", "gender", "class_name"]

ers = (
    ers_normalized
        .select(*SLICE_1_COLS)
        .filter(F.col("sku").isNotNull() & (F.length(F.trim(F.col("sku"))) > 0))
        .withColumn("sku", F.trim(F.col("sku")))
        .dropDuplicates(["sku"])
)
print(f"[INFO] ERS deduplicated row count: {ers.count():,}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Build active SKU set from Shopify

# COMMAND ----------

# Active SKU = appears in order_line for slice 1 window
active_skus = (
    spark.table(SHOPIFY_ORDER_LINE).alias("ol")
         .join(
             spark.table(SHOPIFY_ORDER).alias("o"),
             F.col("ol.order_id") == F.col("o.id"),
             "inner",
         )
         .filter(F.col("o.processed_at") >= F.lit(SLICE_1_START_DATE))
         .filter(F.col("ol.sku").isNotNull() & (F.length(F.trim(F.col("ol.sku"))) > 0))
         .select(F.trim(F.col("ol.sku")).alias("sku"),
                 F.trim(F.col("ol.title")).alias("title_from_shopify"))
         .dropDuplicates(["sku"])
)

active_count = active_skus.count()
print(f"[INFO] Active SKU count (slice 1 window): {active_count:,}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6. Resolve SKUs against ERS (with graceful degradation)
# MAGIC
# MAGIC Three-pass resolution (matches legacy Panoply pattern, `legacy_panoply_etl.md` §2.3):
# MAGIC 1. **Primary**: sku == ERS.sku (exact match — was `unique_identifier` in legacy ERS)
# MAGIC 2. **Fallback**: Shopify title ≈ ERS.item_description (case-insensitive, trimmed)
# MAGIC 3. **Unmatched**: assigned product_key = -1 (logged for review)

# COMMAND ----------

# Pass 1: exact match on canonical sku
pass1 = (
    active_skus.alias("a")
        .join(
            ers.alias("e"),
            F.col("a.sku") == F.col("e.sku"),
            "left"
        )
)

matched_p1 = pass1.filter(F.col("e.vend_id").isNotNull())
unmatched_p1 = pass1.filter(F.col("e.vend_id").isNull()).select("a.sku", "a.title_from_shopify")

print(f"[INFO] Pass 1 (sku exact match): {matched_p1.count():,} matched, "
      f"{unmatched_p1.count():,} unmatched")

# Pass 2: title ≈ item_description (case-insensitive, trimmed)
# This is the legacy Panoply graceful-degradation pattern.
ers_for_pass2 = (
    ers.withColumn("desc_norm", F.lower(F.trim(F.col("item_description"))))
       .dropDuplicates(["desc_norm"])  # avoid multiplicity if duplicate descriptions
)

pass2 = (
    unmatched_p1.alias("u")
        .withColumn("title_norm", F.lower(F.trim(F.col("title_from_shopify"))))
        .join(
            ers_for_pass2.alias("e2"),
            F.col("title_norm") == F.col("e2.desc_norm"),
            "left"
        )
)

matched_p2 = pass2.filter(F.col("e2.vend_id").isNotNull())
unmatched_p2 = pass2.filter(F.col("e2.vend_id").isNull()).select("u.sku")

print(f"[INFO] Pass 2 (title ≈ desc fallback): {matched_p2.count():,} matched, "
      f"{unmatched_p2.count():,} still unmatched")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 7. Assemble dim_product
# MAGIC
# MAGIC - Row 1: sentinel (-1, "Unknown")
# MAGIC - Rows 2+: union of pass1 matches + pass2 matches
# MAGIC - Add surrogate `product_key` via `row_number()` + offset

# COMMAND ----------

# Matched rows from pass 1
matched_p1_clean = matched_p1.select(
    F.col("a.sku").alias("sku"),
    F.col("e.vend_id"),
    F.col("e.item_description"),
    F.col("e.season"),
    F.col("e.group_name"),
    F.col("e.gender"),
    F.col("e.class_name"),
    F.lit("ers_exact").alias("match_source"),
)

# Matched rows from pass 2
matched_p2_clean = matched_p2.select(
    F.col("u.sku").alias("sku"),
    F.col("e2.vend_id"),
    F.col("e2.item_description"),
    F.col("e2.season"),
    F.col("e2.group_name"),
    F.col("e2.gender"),
    F.col("e2.class_name"),
    F.lit("title_fallback").alias("match_source"),
)

all_matched = matched_p1_clean.unionByName(matched_p2_clean)

# Generate surrogate key starting from SURROGATE_KEY_OFFSET
w = Window.orderBy("sku")
dim_with_key = all_matched.withColumn(
    "product_key",
    (F.row_number().over(w) + (SURROGATE_KEY_OFFSET - 1)).cast("int")
)

# Sentinel row for unknown — schema must match dim_with_key exactly
sentinel_row = spark.createDataFrame(
    [(-1, "UNKNOWN", "UNKNOWN", "Unknown product", None, None, None, None, "sentinel")],
    ["product_key", "sku", "vend_id", "item_description",
     "season", "group_name", "gender", "class_name", "match_source"]
)
# Reorder to match dim_with_key column order
sentinel_row = sentinel_row.select(dim_with_key.columns)

dim_final = sentinel_row.unionByName(dim_with_key)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 8. Coverage DQ check

# COMMAND ----------

resolved_count = all_matched.count()
coverage_pct = resolved_count / active_count if active_count > 0 else 0.0
print(f"[INFO] Coverage: {resolved_count:,} / {active_count:,} = {coverage_pct:.4%}")

if coverage_pct < MIN_COVERAGE_PCT:
    print(f"[WARN] Coverage {coverage_pct:.2%} is below threshold {MIN_COVERAGE_PCT:.2%}. "
          f"Unmatched SKUs will resolve to product_key = -1 at fact-build time.")
else:
    print(f"[OK] Coverage threshold met")

# Log unmatched SKUs for visibility
unmatched_count = unmatched_p2.count()
if unmatched_count > 0:
    print(f"[INFO] Sample of {min(20, unmatched_count)} unmatched SKUs:")
    unmatched_p2.limit(20).show(truncate=False)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 9. Write Delta table

# COMMAND ----------

print(f"[INFO] Writing to {FULL_TARGET}")

(
    dim_final
        .write
        .format("delta")
        .mode("overwrite")
        .option("overwriteSchema", "true")
        .saveAsTable(FULL_TARGET)
)

print(f"[OK] Write complete")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 10. Post-write validation

# COMMAND ----------

written = spark.table(FULL_TARGET)
written_count = written.count()
print(f"[INFO] dim_product final row count: {written_count:,}")

# PK uniqueness
distinct_keys = written.select("product_key").distinct().count()
assert distinct_keys == written_count, (
    f"product_key not unique: {written_count} rows, {distinct_keys} distinct keys"
)

# Sentinel row exists
sentinel_present = written.filter(F.col("product_key") == -1).count()
assert sentinel_present == 1, (
    f"Sentinel -1 row missing or duplicated (found {sentinel_present})"
)

# match_source breakdown for visibility
print("[INFO] match_source breakdown:")
written.groupBy("match_source").count().orderBy(F.col("count").desc()).show()

print("[INFO] Sample rows:")
written.orderBy("product_key").limit(10).show(truncate=False)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 11. Summary
# MAGIC
# MAGIC | Metric | Value |
# MAGIC |---|---|
# MAGIC | Target table | `mvdevdatabricks.analytics_platform_32degrees.dim_product` |
# MAGIC | SCD type | Type 1 (overwrite) — Decision 12 |
# MAGIC | ERS schema versions supported | legacy + current (auto-detected) |
# MAGIC | Match strategy | exact sku → title fallback → -1 sentinel |
# MAGIC | Coverage threshold | ≥ 99% of active SKUs |
# MAGIC | Surrogate key range | -1 (sentinel), 1000+ (real products) |
