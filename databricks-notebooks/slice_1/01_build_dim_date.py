# Databricks notebook source
# MAGIC %md
# MAGIC # Slice 1 — Notebook 01: Build `dim_date`
# MAGIC
# MAGIC **Purpose**: Generate `dim_date` directly in PySpark using Python's
# MAGIC `datetime.isocalendar()` and write it as a Delta table.
# MAGIC
# MAGIC **Why in-notebook generation, not read-from-file**:
# MAGIC `dim_date` has no real upstream source — it is a pure calendar.
# MAGIC The original design read a pre-generated Parquet from a Volume, but
# MAGIC `analytics_platform_32degrees` has no Volume. Since `dim_date` is
# MAGIC purely algorithmic, embedding the generation logic is cleaner:
# MAGIC zero external file dependencies, fully self-contained, re-runnable anywhere.
# MAGIC The ISO 8601 boundary logic (Python `isocalendar()`) is identical to
# MAGIC `scripts/generate_dim_date.py` — that script stays in repo as local
# MAGIC validation artifact.
# MAGIC
# MAGIC **Output**: `mvdevdatabricks.analytics_platform_32degrees.dim_date`
# MAGIC
# MAGIC **Idempotent**: Yes — `mode("overwrite")` makes re-runs safe.
# MAGIC
# MAGIC **Author**: Sia Song
# MAGIC **Created**: 2026-05-19
# MAGIC **Updated**: 2026-05-20 — switched from Volume Parquet to in-notebook generation

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Configuration

# COMMAND ----------

TARGET_CATALOG = "mvdevdatabricks"
TARGET_SCHEMA  = "analytics_platform_32degrees"
TARGET_TABLE   = "dim_date"
FULL_TARGET    = f"{TARGET_CATALOG}.{TARGET_SCHEMA}.{TARGET_TABLE}"

# Date range: wider than Slice 1 ETL window (2025-07-01+).
# dim_date is a conformed dimension future-proofed for all slices.
DATE_START = "2023-01-01"
DATE_END   = "2030-12-31"

# Expected row count for assertion
EXPECTED_ROW_COUNT = 2922   # 2023-01-01 to 2030-12-31 inclusive

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Generate dim_date in PySpark
# MAGIC
# MAGIC Uses Python `datetime.isocalendar()` for deterministic ISO 8601 semantics —
# MAGIC same algorithm as `scripts/generate_dim_date.py`.

# COMMAND ----------

from datetime import date, timedelta
from pyspark.sql import Row
from pyspark.sql import functions as F

def generate_dim_date_rows(start: str, end: str) -> list[Row]:
    """
    Generate one Row per calendar date between start and end (inclusive).
    ISO 8601: week starts Monday, week belongs to the year containing its Thursday.
    Identical logic to scripts/generate_dim_date.py.
    """
    rows = []
    current = date.fromisoformat(start)
    end_date = date.fromisoformat(end)

    while current <= end_date:
        iso_year, iso_week, iso_dow = current.isocalendar()

        rows.append(Row(
            date_key        = int(current.strftime("%Y%m%d")),  # e.g. 20230101
            date_actual     = current.isoformat(),               # e.g. "2023-01-01"
            iso_year        = iso_year,
            iso_week        = iso_week,
            iso_day_of_week = iso_dow,                           # 1=Mon … 7=Sun
            cal_year        = current.year,
            cal_month       = current.month,
            cal_day         = current.day,
            cal_quarter     = (current.month - 1) // 3 + 1,
            month_name      = current.strftime("%B"),            # e.g. "January"
            day_name        = current.strftime("%A"),            # e.g. "Monday"
            is_weekend      = iso_dow >= 6,                      # Sat=6, Sun=7
        ))
        current += timedelta(days=1)

    return rows

print(f"[INFO] Generating dim_date rows: {DATE_START} → {DATE_END}")
rows = generate_dim_date_rows(DATE_START, DATE_END)
print(f"[INFO] Generated {len(rows):,} rows in Python")

df = spark.createDataFrame(rows)
print("[INFO] Spark DataFrame created. Schema:")
df.printSchema()

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Pre-write assertions

# COMMAND ----------

source_count = df.count()
assert source_count == EXPECTED_ROW_COUNT, (
    f"Row count mismatch: expected {EXPECTED_ROW_COUNT}, got {source_count}. "
    f"Check DATE_START / DATE_END config."
)

# date_key uniqueness
distinct_count = df.select("date_key").distinct().count()
assert distinct_count == source_count, (
    f"date_key not unique: {source_count} rows, {distinct_count} distinct keys."
)

# ----- ISO 8601 boundary spot checks -----
# Classic edge case: late-December calendar dates can belong to the FIRST
# ISO week of the NEXT year (ISO weeks belong to the year containing Thursday).

# Check 1: 2024-12-30 (Mon) → ISO 2025-W01
spot1 = df.filter(F.col("date_key") == 20241230).select("iso_year", "iso_week").first()
assert spot1 is not None, "date 2024-12-30 missing from dim_date"
assert spot1["iso_year"] == 2025, f"Expected iso_year=2025 for 2024-12-30, got {spot1['iso_year']}"
assert spot1["iso_week"] == 1,    f"Expected iso_week=1 for 2024-12-30, got {spot1['iso_week']}"

# Check 2: 2025-12-29 (Mon) → ISO 2026-W01  ← inside Slice 1 production window
spot2 = df.filter(F.col("date_key") == 20251229).select("iso_year", "iso_week").first()
assert spot2 is not None, "date 2025-12-29 missing from dim_date"
assert spot2["iso_year"] == 2026, f"Expected iso_year=2026 for 2025-12-29, got {spot2['iso_year']}"
assert spot2["iso_week"] == 1,    f"Expected iso_week=1 for 2025-12-29, got {spot2['iso_week']}"

print("[OK] All pre-write assertions passed")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Write Delta table

# COMMAND ----------

print(f"[INFO] Writing to {FULL_TARGET} ...")

(
    df.write
      .format("delta")
      .mode("overwrite")
      .option("overwriteSchema", "true")
      .saveAsTable(FULL_TARGET)
)

print("[OK] Write complete")

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
# MAGIC | Generation method | In-notebook PySpark (no Volume dependency) |
# MAGIC | Rows written | 2,922 |
# MAGIC | Date range | 2023-01-01 to 2030-12-31 (conformed dim, future-proof) |
# MAGIC | ISO week semantics | ISO 8601 (Monday-start, Decision 11) |
# MAGIC | ISO boundary spot checks | 2024-12-30 → 2025-W01 ✓, 2025-12-29 → 2026-W01 ✓ |
# MAGIC | Write mode | overwrite (idempotent) |