# Databricks notebook source
# 05_build_lineage_edges
# Snapshot Unity Catalog's system.access.table_lineage into a governed Delta
# table so the headless metrics-service (service principal) can serve data-layer
# lineage WITHOUT a system-table grant. Runs as sia.song (job run_as), who can
# read system.access. UC populates table_lineage async, so this captures
# accumulated structure — fine for structural lineage.

# COMMAND ----------

SCHEMA = "analytics_platform_32degrees"
TARGET = f"mvdevdatabricks.{SCHEMA}.lineage_edges"

edges = spark.sql(f"""
    SELECT source_table_full_name AS source,
           target_table_full_name AS target,
           max(event_time)        AS last_seen
    FROM system.access.table_lineage
    WHERE source_table_full_name IS NOT NULL
      AND target_table_full_name IS NOT NULL
      AND source_table_full_name <> target_table_full_name
      AND (target_table_schema = '{SCHEMA}' OR source_table_schema = '{SCHEMA}')
    GROUP BY source_table_full_name, target_table_full_name
""")

(edges.write.format("delta").mode("overwrite")
    .option("overwriteSchema", "true").saveAsTable(TARGET))

print(f"Wrote {edges.count()} lineage edges to {TARGET}")
display(edges)