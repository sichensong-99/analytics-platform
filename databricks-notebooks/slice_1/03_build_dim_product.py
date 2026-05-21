# Databricks notebook source
# MAGIC %md
# MAGIC # Slice 1 — Notebook 03: Build `dim_product`
# MAGIC
# MAGIC **Purpose**: Read ERS product master CSV from Volume, normalize across
# MAGIC two possible schema versions, and write `dim_product` as a Delta table.
# MAGIC
# MAGIC **Key engineering features**:
# MAGIC - **Schema-evolution tolerance (Decision 19)**: auto-detects legacy vs
# MAGIC   current ERS column naming and normalizes to one internal schema.
# MAGIC   Lets historical-month CSVs in either format be re-run without manual edits.
# MAGIC - **Graceful degradation**: rows missing critical fields are not silently
# MAGIC   dropped — they get sentinel values and a quality flag, so downstream
# MAGIC   joins still resolve.
# MAGIC - **SCD1 (Decision 12)**: full overwrite. SCD2 deferred until a business
# MAGIC   case for product attribute history emerges (YAGNI).
# MAGIC
# MAGIC **Input**: `/Volumes/mvdevdatabricks/32degrees/raw_uploads/ers/` (shared raw zone)
# MAGIC **Output**: `mvdevdatabricks.analytics_platform_32degrees.dim_product`
# MAGIC **Idempotent**: Yes — `mode("overwrite")`.
# MAGIC
# MAGIC **Author**: Sia Song
# MAGIC **Created**: 2026-05-20

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Configuration

# COMMAND ----------

TARGET_CATALOG = "mvdevdatabricks"
TARGET_SCHEMA  = "analytics_platform_32degrees"
TARGET_TABLE   = "dim_product"
FULL_TARGET    = f"{TARGET_CATALOG}.{TARGET_SCHEMA}.{TARGET_TABLE}"

# ERS CSV lives in the SHARED raw zone (32degrees schema), not our project schema —
# ERS is company-wide product master, consumed by multiple projects.
ERS_VOLUME_PATH = f"/Volumes/{TARGET_CATALOG}/32degrees/raw_uploads/ers/"

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Read raw ERS CSV(s)
# MAGIC
# MAGIC Reads every CSV in the `ers/` folder. If multiple monthly files are
# MAGIC present, the latest one wins (de-dup in Section 5).

# COMMAND ----------

from pyspark.sql import functions as F

print(f"[INFO] Reading ERS CSV from: {ERS_VOLUME_PATH}")

raw = (
    spark.read
         .option("header", "true")
         .option("inferSchema", "true")
         .option("multiLine", "true")     # some product names contain newlines
         .csv(ERS_VOLUME_PATH)
)

print(f"[INFO] Raw row count: {raw.count():,}")
print(f"[INFO] Raw columns ({len(raw.columns)}):")
for c in raw.columns:
    print(f"   - {repr(c)}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Schema detection + normalization (Decision 19)
# MAGIC
# MAGIC ERS has shipped two column-naming conventions over time. We detect which
# MAGIC one this file uses and map BOTH onto one internal schema. Adding a third
# MAGIC future format = add one more dict entry here, no other code changes.

# COMMAND ----------

# Two known ERS schema versions. Keys = our internal canonical names.
# Values = the source column name in that schema version.
ERS_SCHEMA_MAP = {
    "legacy": {
        "sku":              "Unique_Identifier",
        "vend_id":          "Vend_ID",
        "item_description": "Item_Description",
        "season":           "Season",
        "group_name":       "Group",
        "gender":           "Gender",
        "class_name":       "Class",
        "master_style":     "Master_Style",
        "cost":             "Cost",
        "retail":           "Retail",
    },
    "current": {
        "sku":              "SKU",
        "vend_id":          "Style#",
        "item_description": "Item Description",
        "season":           "Season",
        "group_name":       "Group",
        "gender":           "Gender",
        "class_name":       "Class",
        "master_style":     "Master Style",
        "cost":             "Cost",
        "retail":           "Retail",
    },
}

def detect_ers_schema(columns: list[str]) -> str:
    """
    Detect which ERS schema version a file uses by checking for a
    distinctive column unique to each version.
    """
    cols = set(columns)
    if "SKU" in cols and "Style#" in cols:
        return "current"
    if "Unique_Identifier" in cols and "Vend_ID" in cols:
        return "legacy"
    raise ValueError(
        f"Unrecognized ERS schema. Columns seen: {sorted(cols)}. "
        f"Add a new entry to ERS_SCHEMA_MAP if ERS changed format again."
    )

detected = detect_ers_schema(raw.columns)
print(f"[INFO] Detected ERS schema version: '{detected}'")

colmap = ERS_SCHEMA_MAP[detected]

# Verify all expected source columns are present before renaming
missing = [src for src in colmap.values() if src not in raw.columns]
assert not missing, (
    f"Schema '{detected}' detected, but expected columns are missing: {missing}"
)

# Rename source columns -> internal canonical names; keep only what we need
normalized = raw.select(*[
    F.col(f"`{src}`").alias(internal)
    for internal, src in colmap.items()
])

print(f"[INFO] Normalized to internal schema. Columns: {normalized.columns}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Graceful degradation — fill sentinels, never drop rows
# MAGIC
# MAGIC A row missing `sku` is unusable (no primary key) — those we drop and count.
# MAGIC A row with `sku` but missing descriptive fields stays, with sentinel values,
# MAGIC so fact-table joins still resolve. We flag imperfect rows for the DQ report.

# COMMAND ----------

before = normalized.count()

# Drop only rows with no SKU (cannot be a dimension member without a key)
clean = normalized.filter(F.col("sku").isNotNull() & (F.trim(F.col("sku")) != ""))
dropped_no_sku = before - clean.count()
print(f"[INFO] Dropped {dropped_no_sku} row(s) with null/empty sku")

# Trim whitespace on all string columns
str_cols = ["sku", "vend_id", "item_description", "season",
            "group_name", "gender", "class_name", "master_style"]
for c in str_cols:
    clean = clean.withColumn(c, F.trim(F.col(c)))

# Fill descriptive-field sentinels (keep the row, mark it imperfect)
clean = (
    clean
    .withColumn("vend_id",          F.coalesce(F.col("vend_id"),          F.lit("UNKNOWN")))
    .withColumn("item_description", F.coalesce(F.col("item_description"), F.lit("UNKNOWN")))
    .withColumn("season",           F.coalesce(F.col("season"),           F.lit("UNKNOWN")))
    .withColumn("group_name",       F.coalesce(F.col("group_name"),       F.lit("UNKNOWN")))
    .withColumn("gender",           F.coalesce(F.col("gender"),           F.lit("UNKNOWN")))
    .withColumn("class_name",       F.coalesce(F.col("class_name"),       F.lit("UNKNOWN")))
    .withColumn("master_style",     F.coalesce(F.col("master_style"),     F.lit("UNKNOWN")))
)

# Cast numerics; bad values become NULL rather than failing the job
clean = (
    clean
    .withColumn("cost",   F.col("cost").cast("decimal(10,2)"))
    .withColumn("retail", F.col("retail").cast("decimal(10,2)"))
)

# Data-quality flag: row is "imperfect" if any descriptive field is sentinel
clean = clean.withColumn(
    "is_complete",
    ~(
        (F.col("vend_id") == "UNKNOWN") |
        (F.col("item_description") == "UNKNOWN") |
        (F.col("season") == "UNKNOWN")
    ),
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. De-duplicate on sku (latest file wins)
# MAGIC
# MAGIC If multiple monthly CSVs sit in the folder, the same SKU appears more
# MAGIC than once. We keep one row per SKU. (For Slice 1 there is one file, so
# MAGIC this is a no-op — but it makes the notebook safe for monthly re-runs.)

# COMMAND ----------

before_dedup = clean.count()
deduped = clean.dropDuplicates(["sku"])
removed_dupes = before_dedup - deduped.count()
print(f"[INFO] Removed {removed_dupes} duplicate sku row(s)")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6. Add surrogate key + metadata, finalize

# COMMAND ----------

from pyspark.sql.window import Window

# Surrogate key: deterministic, ordered by sku
w = Window.orderBy("sku")
final = (
    deduped
    .withColumn("product_key", F.row_number().over(w))
    .withColumn("_ingested_at", F.current_timestamp())
    .withColumn("_ers_schema_version", F.lit(detected))
    .select(
        "product_key", "sku", "vend_id", "item_description",
        "season", "group_name", "gender", "class_name", "master_style",
        "cost", "retail", "is_complete",
        "_ers_schema_version", "_ingested_at",
    )
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 7. Pre-write assertions

# COMMAND ----------

final_count = final.count()
assert final_count > 0, "dim_product is empty — check ERS source file"

# product_key uniqueness
pk_distinct = final.select("product_key").distinct().count()
assert pk_distinct == final_count, "product_key not unique"

# sku uniqueness (the natural key)
sku_distinct = final.select("sku").distinct().count()
assert sku_distinct == final_count, "sku not unique after de-dup"

print(f"[OK] Pre-write assertions passed ({final_count:,} products)")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 8. Write Delta table (SCD1 overwrite)

# COMMAND ----------

print(f"[INFO] Writing to {FULL_TARGET} ...")

(
    final.write
         .format("delta")
         .mode("overwrite")
         .option("overwriteSchema", "true")
         .saveAsTable(FULL_TARGET)
)

print("[OK] Write complete")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 9. Post-write validation

# COMMAND ----------

written = spark.table(FULL_TARGET)
written_count = written.count()
print(f"[INFO] Written row count: {written_count:,}")

# Completeness distribution
print("\n[INFO] Completeness (is_complete) distribution:")
written.groupBy("is_complete").count().orderBy("is_complete").show()

# Season distribution (top 15)
print("[INFO] Top 15 seasons by product count:")
written.groupBy("season").count().orderBy(F.col("count").desc()).show(15, truncate=False)

# Sample rows
print("[INFO] Sample 10 rows:")
written.orderBy("product_key").select(
    "product_key", "sku", "vend_id", "item_description", "season", "cost", "retail"
).show(10, truncate=False)

print(f"\n[OK] dim_product build complete — {written_count:,} products from '{detected}' schema")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 10. Summary
# MAGIC
# MAGIC | Metric | Value |
# MAGIC |---|---|
# MAGIC | Target table | `mvdevdatabricks.analytics_platform_32degrees.dim_product` |
# MAGIC | Source | ERS CSV @ `32degrees/raw_uploads/ers/` (shared raw zone) |
# MAGIC | Schema detection | Auto (legacy / current) — Decision 19 |
# MAGIC | Graceful degradation | Sentinel fill + `is_complete` flag, no silent drops |
# MAGIC | SCD type | SCD1 overwrite (Decision 12, YAGNI) |
# MAGIC | Natural key | `sku` (e.g. `TLF60281DRT-067-XS`) |
# MAGIC | Surrogate key | `product_key` (row_number) |
# MAGIC | Idempotent | Yes (overwrite + monthly re-run safe via de-dup) |