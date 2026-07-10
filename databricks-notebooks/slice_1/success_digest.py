# Databricks notebook source
# MAGIC %md
# MAGIC # Slice 1 — Success Digest
# MAGIC
# MAGIC Runs at the end of a successful DAG. Two jobs:
# MAGIC 1. Post a brief health summary to Slack (passive visibility for the leader:
# MAGIC    "the platform is running", plus slow trends like row-count / runtime drift).
# MAGIC 2. Record today's fact row count so tomorrow can compute a day-over-day delta.
# MAGIC
# MAGIC Slack posting **gracefully no-ops** until the webhook secret is configured
# MAGIC (that happens in Step 3). So this task is safe to run now — it just prints
# MAGIC the digest to the task log and skips the Slack call.
# MAGIC
# MAGIC Uses `urllib` (stdlib) for the Slack POST — no extra dependency.

# COMMAND ----------

import json
import urllib.request
from datetime import datetime, timezone
from pyspark.sql import functions as F

# COMMAND ----------

dbutils.widgets.text("fact_fqn", "analytics_catalog.analytics_platform.fact_orders_line")
dbutils.widgets.text("history_fqn", "analytics_catalog.analytics_platform.pipeline_run_history")
dbutils.widgets.text("report_dir", "dbfs:/tmp/dq_reports")

FACT_FQN = dbutils.widgets.get("fact_fqn")
HISTORY_FQN = dbutils.widgets.get("history_fqn")
REPORT_DIR = dbutils.widgets.get("report_dir").rstrip("/")

# COMMAND ----------

# Ensure the run-history table exists (self-contained; first run creates it).
spark.sql(
    f"""
    CREATE TABLE IF NOT EXISTS {HISTORY_FQN} (
        run_date         DATE,
        fact_row_count   BIGINT,
        dq_summary       STRING,
        recorded_at_utc  TIMESTAMP
    ) USING DELTA
    """
)

today_count = spark.table(FACT_FQN).count()

# Most recent prior day's count, for the delta.
prev = (
    spark.table(HISTORY_FQN)
    .filter(F.col("run_date") < F.current_date())
    .orderBy(F.col("run_date").desc())
    .limit(1)
    .collect()
)
yesterday_count = prev[0]["fact_row_count"] if prev else today_count
delta = today_count - yesterday_count

# COMMAND ----------

# Best-effort: pull the latest DQ report summary written by the dq_gate task.
dq_summary = "n/a"
try:
    files = [f for f in dbutils.fs.ls(REPORT_DIR) if f.name.startswith("dq_report_")]
    if files:
        latest = sorted(files, key=lambda f: f.modificationTime)[-1]
        content = json.loads(dbutils.fs.head(latest.path, 256 * 1024))
        dq_summary = (
            f"{content.get('passed')}/{content.get('total_checks')} passed, "
            f"{content.get('warnings')} warn, {content.get('hard_failures')} fail"
        )
except Exception as e:
    print(f"[INFO] could not read DQ report: {e}")

# COMMAND ----------

sign = "+" if delta >= 0 else ""
msg = (
    f":white_check_mark: Analytics Pipeline OK — {datetime.now(timezone.utc).strftime('%Y-%m-%d')}\n"
    f"   • fact_orders_line: {today_count:,} rows ({sign}{delta:,} vs prev)\n"
    f"   • DQ: {dq_summary}"
)
print(msg)

# COMMAND ----------

# Post to Slack only if the webhook secret is configured (Step 3 sets this).
webhook = None
try:
    webhook = dbutils.secrets.get("analytics-platform", "slack-webhook-url")
except Exception:
    pass

if webhook:
    try:
        data = json.dumps({"text": msg}).encode("utf-8")
        req = urllib.request.Request(
            webhook, data=data, headers={"Content-Type": "application/json"}
        )
        urllib.request.urlopen(req, timeout=5)
        print("[INFO] digest posted to Slack")
    except Exception as e:
        print(f"[WARN] Slack post failed: {e}")
else:
    print("[INFO] Slack webhook secret not set yet — skipping post (enable in Step 3).")

# COMMAND ----------

# Record today's count (idempotent for same-day reruns: delete-then-insert today).
spark.sql(f"DELETE FROM {HISTORY_FQN} WHERE run_date = current_date()")
spark.createDataFrame(
    [(datetime.now(timezone.utc).date(), int(today_count), dq_summary, datetime.now(timezone.utc))],
    "run_date date, fact_row_count bigint, dq_summary string, recorded_at_utc timestamp",
).write.mode("append").saveAsTable(HISTORY_FQN)

print(f"[INFO] recorded {today_count:,} rows for {datetime.now(timezone.utc).date()}")
