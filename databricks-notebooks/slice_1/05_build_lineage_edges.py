# Databricks notebook source
# 05_build_lineage_edges  —  incremental / watermark-based
# =============================================================================
# Snapshot Unity Catalog's system.access.table_lineage into a governed Delta
# table (lineage_edges) so the headless metrics-service (service principal) can
# serve data-layer lineage WITHOUT a direct system-table grant. This notebook
# runs as sia.song (job "run as"), who can read system.access; the deployed
# service principal cannot, so it reads our curated lineage_edges instead.
#
# 2026-06-10 — changed from FULL-SCAN + OVERWRITE to INCREMENTAL + MERGE.
#   Root cause of the daily-job failure: system.access.table_lineage keeps a
#   rolling 1-year window and grows every day. The old unfiltered scan got
#   slower over time until the lineage_edges task crossed its 10-min timeout
#   and failed the whole slice_1_daily run.
#   Fix: scan only RECENT partitions (event_date is a partitioned column, so
#   this prunes the read to a few days) and MERGE into lineage_edges. Edges we
#   already captured are preserved; only last_seen is refreshed. Same
#   idempotent-MERGE + watermark pattern we use on fact_orders_line.
# =============================================================================

# COMMAND ----------

from delta.tables import DeltaTable
from pyspark.sql import functions as F
from datetime import timedelta

SCHEMA = "analytics_platform"
TARGET = f"analytics_catalog.{SCHEMA}.lineage_edges"

# Re-scan this many days behind the watermark every run. UC writes lineage
# asynchronously, so an event can land a day or two after it happened; a small
# buffer catches late arrivals without paying for a full scan.
SAFETY_BUFFER_DAYS = 3

# Window used only on the very first run / if lineage_edges is missing or empty.
# 365 = the system table's full retention.
BOOTSTRAP_LOOKBACK_DAYS = 365

# COMMAND ----------

# --- 1. Decide how far back to scan (the watermark) --------------------------
target_exists = spark.catalog.tableExists(TARGET)

start_date = None  # None => use the bootstrap window below
if target_exists:
    wm_date = spark.sql(
        f"SELECT date(max(last_seen)) AS wm_date FROM {TARGET}"
    ).collect()[0]["wm_date"]
    if wm_date is not None:
        start_date = wm_date - timedelta(days=SAFETY_BUFFER_DAYS)

if start_date is not None:
    lower_bound = f"date('{start_date.isoformat()}')"
else:
    lower_bound = f"date_sub(current_date(), {BOOTSTRAP_LOOKBACK_DAYS})"

print(f"target_exists={target_exists} | scanning event_date >= {lower_bound}")

# COMMAND ----------

# --- 2. Read only the recent partitions (event_date pruning) -----------------
edges = spark.sql(f"""
    SELECT source_table_full_name AS source,
           target_table_full_name AS target,
           max(event_time)         AS last_seen
    FROM system.access.table_lineage
    WHERE event_date >= {lower_bound}
      AND source_table_full_name IS NOT NULL
      AND target_table_full_name IS NOT NULL
      AND source_table_full_name <> target_table_full_name
      AND (target_table_schema = '{SCHEMA}' OR source_table_schema = '{SCHEMA}')
    GROUP BY source_table_full_name, target_table_full_name
""")

found = edges.count()
print(f"Found {found} edge(s) in the scanned window")

# COMMAND ----------

# --- 3. Upsert into lineage_edges (idempotent MERGE) -------------------------
# matched     -> push last_seen forward to the most recent we've seen
# not matched -> insert the new edge
# edges absent from this window are left untouched -> structural history kept
if not target_exists:
    (edges.write.format("delta").mode("overwrite")
        .option("overwriteSchema", "true").saveAsTable(TARGET))
    print(f"Bootstrapped {TARGET} with {found} edges")
else:
    (DeltaTable.forName(spark, TARGET).alias("t")
        .merge(edges.alias("s"), "t.source = s.source AND t.target = s.target")
        .whenMatchedUpdate(set={
            "last_seen": F.greatest(F.col("t.last_seen"), F.col("s.last_seen"))
        })
        .whenNotMatchedInsertAll()
        .execute())
    total = spark.sql(f"SELECT count(*) AS c FROM {TARGET}").collect()[0]["c"]
    print(f"MERGE complete — lineage_edges now holds {total} edges")

# COMMAND ----------

display(spark.sql(f"SELECT * FROM {TARGET} ORDER BY last_seen DESC"))