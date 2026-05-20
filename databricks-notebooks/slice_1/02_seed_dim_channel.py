# Databricks notebook source
# MAGIC %md
# MAGIC # Slice 1 — Notebook 02: Seed `dim_channel`
# MAGIC
# MAGIC **Purpose**: Populate the `dim_channel` table from the version-controlled seed SQL file.
# MAGIC
# MAGIC **Why seed-driven**: `dim_channel` is small (~16 rows) and content-controlled (channel
# MAGIC taxonomy is a business-decision artifact, not raw data). Keeping the seed in a SQL file
# MAGIC under version control gives auditability (who changed which channel and when).
# MAGIC
# MAGIC **Input**: `docs/data_modeling/dim_channel_seed.sql` (committed in git repo)
# MAGIC
# MAGIC **Output**: `mvdevdatabricks.analytics_platform_32degrees.dim_channel`
# MAGIC
# MAGIC **Idempotent**: Yes — seed SQL is `TRUNCATE + INSERT`.
# MAGIC
# MAGIC **Note**: For Phase 4 Workflows orchestration, this notebook will be triggered by a
# MAGIC job task that mounts the repo (Databricks Repos) so the SQL file is accessible at a
# MAGIC stable path. For slice 1 manual runs, paste the seed SQL inline if Repos mount is not
# MAGIC yet configured (see §3 fallback).
# MAGIC
# MAGIC **Author**: Sia Song
# MAGIC **Created**: 2026-05-19

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Configuration

# COMMAND ----------

TARGET_CATALOG = "mvdevdatabricks"
TARGET_SCHEMA = "analytics_platform_32degrees"
TARGET_TABLE = "dim_channel"

FULL_TARGET = f"{TARGET_CATALOG}.{TARGET_SCHEMA}.{TARGET_TABLE}"

# Path to the seed SQL file once Databricks Repos is mounted.
# Adjust to the actual mounted path in your workspace; placeholder shown:
SEED_SQL_PATH = "/Workspace/Repos/sia.song/analytics-platform/docs/data_modeling/dim_channel_seed.sql"

# Expected row count post-seed (sync with dim_channel_seed.sql contents)
EXPECTED_ROW_COUNT = 16

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Read seed SQL
# MAGIC
# MAGIC **Primary path**: Read from mounted git repo.
# MAGIC **Fallback**: If Repos not mounted, manually paste the seed SQL into the SEED_SQL_INLINE
# MAGIC variable below and set USE_INLINE = True.

# COMMAND ----------

USE_INLINE = False  # Flip True if Repos mount is unavailable

SEED_SQL_INLINE = """
-- PASTE CONTENTS OF dim_channel_seed.sql HERE IF USE_INLINE = True
-- (intentionally left empty; populate at runtime if needed)
"""

if USE_INLINE:
    seed_sql = SEED_SQL_INLINE
    print("[INFO] Using inline seed SQL")
else:
    with open(SEED_SQL_PATH, "r", encoding="utf-8") as f:
        seed_sql = f.read()
    print(f"[INFO] Loaded seed SQL from: {SEED_SQL_PATH}")
    print(f"[INFO] Seed SQL length: {len(seed_sql)} chars")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Execute seed SQL
# MAGIC
# MAGIC Split the file into individual statements on `;` and execute each via `spark.sql`.

# COMMAND ----------

# Strip SQL comments (lines starting with --) and empty lines, then split on ;
def split_sql_statements(sql_text: str) -> list[str]:
    """Naive SQL splitter: removes -- line comments, splits on ; , keeps non-empty."""
    cleaned_lines = []
    for line in sql_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("--") or stripped == "":
            continue
        cleaned_lines.append(line)
    cleaned = "\n".join(cleaned_lines)
    statements = [s.strip() for s in cleaned.split(";") if s.strip()]
    return statements

statements = split_sql_statements(seed_sql)
print(f"[INFO] {len(statements)} SQL statements to execute")

for i, stmt in enumerate(statements, start=1):
    preview = stmt[:80].replace("\n", " ")
    print(f"[INFO] Executing statement {i}/{len(statements)}: {preview}...")
    spark.sql(stmt)

print("[OK] All statements executed")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Post-write validation

# COMMAND ----------

from pyspark.sql import functions as F

written = spark.table(FULL_TARGET)
written_count = written.count()
print(f"[INFO] dim_channel row count: {written_count}")

assert written_count == EXPECTED_ROW_COUNT, (
    f"Row count mismatch: expected {EXPECTED_ROW_COUNT}, got {written_count}. "
    f"Did you update EXPECTED_ROW_COUNT after editing the seed SQL?"
)

# channel_key uniqueness
distinct_keys = written.select("channel_key").distinct().count()
assert distinct_keys == written_count, (
    f"channel_key not unique: {written_count} rows, {distinct_keys} distinct keys"
)

# channel_source uniqueness (business key)
distinct_sources = written.select("channel_source").distinct().count()
assert distinct_sources == written_count, (
    f"channel_source not unique: {written_count} rows, {distinct_sources} distinct sources"
)

# -1 unknown placeholder row must exist
unknown_row = written.filter(F.col("channel_key") == -1).count()
assert unknown_row == 1, (
    f"Missing -1 'unknown' placeholder row in dim_channel (found {unknown_row})"
)

print("[OK] All post-write assertions passed")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Visual inspection
# MAGIC
# MAGIC Log every distinct `legacy_channel_group` to verify the GA4-style grouping
# MAGIC is what Leader expects to see in the demo.

# COMMAND ----------

print("[INFO] Full dim_channel contents:")
written.orderBy("channel_key").show(50, truncate=False)

print("[INFO] Distinct legacy_channel_group values (sorted):")
(
    written.select("legacy_channel_group")
           .distinct()
           .orderBy("legacy_channel_group")
           .show(50, truncate=False)
)

print("[INFO] Paid vs non-paid breakdown:")
written.groupBy("is_paid").count().show()

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6. Summary
# MAGIC
# MAGIC | Metric | Value |
# MAGIC |---|---|
# MAGIC | Target table | `mvdevdatabricks.analytics_platform_32degrees.dim_channel` |
# MAGIC | Rows written | 16 |
# MAGIC | Includes `-1` unknown placeholder | ✓ |
# MAGIC | Includes Non-attributed / Excluded meta-categories | ✓ (Decision 14) |
# MAGIC | Dual-display fields (channel_source + legacy_channel_group) | ✓ (Decision 15) |
