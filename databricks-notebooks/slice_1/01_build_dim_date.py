# Databricks notebook source
# MAGIC %md
# MAGIC # Slice 1 — Notebook 01: Build `dim_date`
# MAGIC
# MAGIC **Purpose**: Load the pre-generated `dim_date.parquet` from Databricks Volume into the
# MAGIC analytics platform schema as a Delta table.
# MAGIC
# MAGIC **Why pre-generated, not in-warehouse SQL**: Python `datetime.isocalendar()` gives
# MAGIC deterministic ISO 8601 boundary week behavior (Decision 11). SQL date functions vary
# MAGIC across engines and are easier to get wrong on cross-year weeks (W52/W53).
# MAGIC
# MAGIC **Input**: `/Volumes/mvdevdatabricks/analytics_platform_32degrees/raw_uploads/dim_date.parquet`
# MAGIC
# MAGIC **Output**: `mvdevdatabricks.analytics_platform_32degrees.dim_date`
# MAGIC
# MAGIC **Idempotent**: Yes — `mode("overwrite")` makes re-runs safe.
# MAGIC
# MAGIC **Author**: Sia Song
# MAGIC **Created**: 2026-05-19

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Configuration

# COMMAND ----------

# ----- Editable configuration -----
TARGET_CATALOG = "mvdevdatabricks"
TARGET_SCHEMA = "analytics_platform_32degrees"
TARGET_TABLE = "dim_date"

VOLUME_PATH = (
    f"/Volumes/{TARGET_CATALOG}/{TARGET_SCHEMA}/raw_uploads/dim_date.parquet"
)
FULL_TARGET = f"{TARGET_CATALOG}.{TARGET_SCHEMA}.{TARGET_TABLE}"

# Expected row count for assertion (2023-01-01 to 2030-12-31 inclusive)
# Note: dim_date intentionally has wider date range than slice 1's ETL window
# (2025-07-01+). dim_date is a conformed dimension future-proofed for all slices.
EXPECTED_ROW_COUNT = 2922

# ----- Optional toggles -----
FORCE_REBUILD = True   # Always overwrite for slice 1; flip to False once we add incremental logic

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Read source Parquet

# COMMAND ----------

from pyspark.sql import functions as F

print(f"[INFO] Reading dim_date Parquet from: {VOLUME_PATH}")

df = spark.read.parquet(VOLUME_PATH)

print(f"[INFO] Source row count: {df.count():,}")
print(f"[INFO] Source schema:")
df.printSchema()

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Pre-write assertions

# COMMAND ----------

source_count = df.count()
assert source_count == EXPECTED_ROW_COUNT, (
    f"Row count mismatch: expected {EXPECTED_ROW_COUNT}, got {source_count}. "
    f"Has the generate_dim_date.py date range changed?"
)

# date_key uniqueness check
distinct_count = df.select("date_key").distinct().count()
assert distinct_count == source_count, (
    f"date_key not unique: {source_count} rows, {distinct_count} distinct keys."
)

# ----- ISO 8601 boundary spot checks -----
# These verify the classic ISO 8601 edge case: a calendar date in late December
# can belong to the FIRST ISO week of the NEXT year (because ISO weeks belong
# to the year containing their Thursday). Catches off-by-one bugs in the date
# generator.

# Check 1: General edge case (outside slice 1 window) — calibrates dim_date itself
spot_check_general = df.filter(F.col("date_key") == 20241230).select("iso_year", "iso_week").first()
assert spot_check_general is not None, "Spot check date 2024-12-30 not found in dim_date"
assert spot_check_general["iso_year"] == 2025, (
    f"Expected iso_year=2025 for 2024-12-30, got {spot_check_general['iso_year']}"
)
assert spot_check_general["iso_week"] == 1, (
    f"Expected iso_week=1 for 2024-12-30, got {spot_check_general['iso_week']}"
)

# Check 2: Edge case INSIDE slice 1 ETL window — 2025-12-29 (Mon) belongs to ISO 2026-W01.
# This is the actual cross-year ISO edge that production data will hit.
spot_check_slice1 = df.filter(F.col("date_key") == 20251229).select("iso_year", "iso_week").first()
assert spot_check_slice1 is not None, "Spot check date 2025-12-29 not found in dim_date"
assert spot_check_slice1["iso_year"] == 2026, (
    f"Expected iso_year=2026 for 2025-12-29, got {spot_check_slice1['iso_year']}"
)
assert spot_check_slice1["iso_week"] == 1, (
    f"Expected iso_week=1 for 2025-12-29, got {spot_check_slice1['iso_week']}"
)

print("[OK] All pre-write assertions passed")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Write Delta table

# COMMAND ----------

print(f"[INFO] Writing to {FULL_TARGET}")

(
    df.write
      .format("delta")
      .mode("overwrite")
      .option("overwriteSchema", "true")
      .saveAsTable(FULL_TARGET)
)

print(f"[OK] Write complete")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Post-write validation

# COMMAND ----------

written = spark.table(FULL_TARGET)
written_count = written.count()
print(f"[INFO] Written table row count: {written_count:,}")

assert written_count == EXPECTED_ROW_COUNT, (
    f"Post-write count mismatch: expected {EXPECTED_ROW_COUNT}, got {written_count}"
)

# Display first 5 + last 5 rows for human-eyeball sanity
print("[INFO] First 5 rows:")
written.orderBy("date_key").limit(5).show(truncate=False)

print("[INFO] Last 5 rows:")
written.orderBy(F.col("date_key").desc()).limit(5).show(truncate=False)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6. Summary
# MAGIC
# MAGIC | Metric | Value |
# MAGIC |---|---|
# MAGIC | Target table | `mvdevdatabricks.analytics_platform_32degrees.dim_date` |
# MAGIC | Rows written | 2,922 |
# MAGIC | Date range | 2023-01-01 to 2030-12-31 (conformed dim, future-proof) |
# MAGIC | ISO week semantics | ISO 8601 (Monday-start, Decision 11) |
# MAGIC | ISO boundary spot checks | 2024-12-30 → 2025-W01, 2025-12-29 → 2026-W01 |
# MAGIC | Write mode | overwrite (idempotent) |
