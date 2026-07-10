# Databricks notebook source
# MAGIC %md
# MAGIC # Slice 1 — DQ Gate (production, Spark-native)
# MAGIC
# MAGIC **Role in the DAG**: runs after `04_build_fact_orders_line`, before metric refresh.
# MAGIC A hard failure here raises an exception -> this task fails -> downstream tasks
# MAGIC (`metric_refresh`, `success_digest`) are skipped -> bad data never reaches
# MAGIC consumers. The ETL output table is NOT deleted (it stays debuggable).
# MAGIC
# MAGIC **Why this is separate from the inline DQ in notebook 04**
# MAGIC - Inline (notebook 04): developer-runtime safety net, multi-tier WARN/FAIL during ETL.
# MAGIC - This gate: production integrity contract. It REUSES the SAME YAML check specs
# MAGIC   that the pandas DQ framework (`metrics-service/data_quality/`) uses for local /
# MAGIC   unit testing, but executes them in **Spark** so it scales to the ~10M-row fact
# MAGIC   (cannot `.toPandas()` that). Same config contract, different execution engine.
# MAGIC
# MAGIC **Severity model** (calibrated per Decision 18 — avoid alert fatigue / false blocks):
# MAGIC - `not_null` / `unique`  -> FAIL  (PK / integrity broken; blocks the pipeline)
# MAGIC - `range` / `freshness`  -> WARN  (domain sanity / staleness; logged, non-blocking)
# MAGIC - Any single check can override its severity with a `severity:` key in its YAML spec.
# MAGIC
# MAGIC **Parameters** (set from the Workflows task `base_parameters`):
# MAGIC - `dq_config_dir`: workspace folder holding the 4 YAML configs.
# MAGIC - `report_dir`: where the run-id-suffixed JSON report is written.

# COMMAND ----------

# MAGIC %pip install pyyaml --quiet

# COMMAND ----------

import os
import json
import yaml
from datetime import datetime, timezone
from pyspark.sql import functions as F

# COMMAND ----------

# ---- Parameters (overridable from the Workflows task) ----
dbutils.widgets.text("dq_config_dir", "/Workspace/Users/sia.song@example.com/slice_1/dq_configs")
dbutils.widgets.text("report_dir", "dbfs:/tmp/dq_reports")

DQ_CONFIG_DIR = dbutils.widgets.get("dq_config_dir")
REPORT_DIR = dbutils.widgets.get("report_dir").rstrip("/")

# The 4 Slice 1 configs (same files committed under metrics-service/data_quality/configs/)
CONFIG_FILES = [
    "dim_date.yaml",
    "dim_channel.yaml",
    "dim_product.yaml",
    "fact_orders_line.yaml",
]


def _default_severity(check_type: str) -> str:
    """Integrity checks block; domain/staleness checks only warn."""
    return "warn" if check_type in ("freshness", "range") else "fail"


# ---- run id for traceability (DQ report is suffixed with it) ----
try:
    ctx = dbutils.notebook.entry_point.getDbutils().notebook().getContext()
    RUN_ID = ctx.tags().apply("jobRunId")
except Exception:
    RUN_ID = "manual_" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")

print(f"[INFO] DQ Gate run_id = {RUN_ID}")
print(f"[INFO] config dir     = {DQ_CONFIG_DIR}")
print(f"[INFO] report dir     = {REPORT_DIR}")

# COMMAND ----------


def _freshness_col(df, column):
    """Normalize a column to a timestamp for freshness comparison.

    Handles real timestamp/date columns and integer yyyyMMdd date_key columns
    (e.g. dim_date.date_key), so freshness works across all 4 tables.
    """
    dtype = dict(df.dtypes).get(column)
    if dtype == "timestamp":
        return F.col(column)
    if dtype == "date":
        return F.to_timestamp(F.col(column))
    # integer date_key (yyyyMMdd) -> timestamp
    return F.to_timestamp(F.col(column).cast("string"), "yyyyMMdd")


def run_check(table_fqn, df, total, spec):
    """Execute one YAML check spec in Spark, return a result dict."""
    ctype = spec.get("type", "unknown")
    col = spec.get("column")
    severity = spec.get("severity", _default_severity(ctype))
    failed = 0
    detail = ""

    try:
        if ctype == "not_null":
            failed = df.filter(F.col(col).isNull()).count()
            detail = f"{failed} null(s) in {col}"

        elif ctype == "unique":
            dup_rows = (
                df.groupBy(col).count().filter("count > 1")
                .agg(F.coalesce(F.sum("count"), F.lit(0)).alias("n"))
                .first()["n"]
            )
            failed = int(dup_rows or 0)
            detail = f"{failed} row(s) in duplicate groups on {col}"

        elif ctype == "range":
            mn = spec.get("min")
            mx = spec.get("max")
            viol = F.lit(False)
            if mn is not None:
                viol = viol | (F.col(col) < F.lit(mn))
            if mx is not None:
                viol = viol | (F.col(col) > F.lit(mx))
            failed = df.filter(F.col(col).isNotNull() & viol).count()
            detail = f"{failed} value(s) outside [{mn}, {mx}] in {col}"

        elif ctype == "freshness":
            hours = float(spec["max_age_hours"])
            maxts = df.select(F.max(_freshness_col(df, col)).alias("m")).first()["m"]
            if maxts is None:
                failed = 1
                detail = f"no timestamp found in {col}"
            else:
                now = datetime.now(timezone.utc)
                mt = maxts if maxts.tzinfo else maxts.replace(tzinfo=timezone.utc)
                age_h = (now - mt).total_seconds() / 3600.0
                # positive limit: newest record must be younger than `hours`
                # negative limit: data must extend |hours| into the FUTURE (dim_date coverage)
                ok = age_h <= hours
                failed = 0 if ok else 1
                if hours >= 0:
                    detail = f"max({col}) age {age_h:.1f}h (limit {hours}h)"
                else:
                    detail = f"max({col}) age {age_h:.1f}h (must extend into future, limit {hours}h)"

        else:
            severity = "warn"
            failed = 0
            detail = f"unknown check type '{ctype}' — skipped"

    except Exception as e:
        # A check that errors is itself a failure of its declared severity.
        failed = -1
        detail = f"check error: {e}"

    return {
        "table_fqn": table_fqn,
        "type": ctype,
        "column": col,
        "severity": severity,
        "passed": failed == 0,
        "failed_count": failed,
        "total_count": total,
        "detail": detail,
    }


# COMMAND ----------

results = []

for fname in CONFIG_FILES:
    path = os.path.join(DQ_CONFIG_DIR, fname)
    # Workspace files are readable via their /Workspace POSIX path.
    with open(path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    table_fqn = cfg["table_fqn"]
    df = spark.table(table_fqn)
    total = df.count()
    print(f"\n=== {fname}  ->  {table_fqn}  ({total:,} rows) ===")

    for spec in cfg.get("checks", []):
        r = run_check(table_fqn, df, total, spec)
        results.append(r)
        status = "PASS" if r["passed"] else ("FAIL" if r["severity"] == "fail" else "WARN")
        print(f"  [{status:4}] {r['type']:9} {str(r['column']):22} {r['detail']}")

# COMMAND ----------

hard_fails = [r for r in results if r["severity"] == "fail" and not r["passed"]]
warns = [r for r in results if r["severity"] == "warn" and not r["passed"]]
n_pass = sum(1 for r in results if r["passed"])

summary = {
    "run_id": RUN_ID,
    "checked_at_utc": datetime.now(timezone.utc).isoformat(),
    "total_checks": len(results),
    "passed": n_pass,
    "warnings": len(warns),
    "hard_failures": len(hard_fails),
    "results": results,
}

# ---- write JSON report (run-id suffixed, for forensic traceability) ----
try:
    dbutils.fs.mkdirs(REPORT_DIR)
    report_path = f"{REPORT_DIR}/dq_report_{RUN_ID}.json"
    dbutils.fs.put(report_path, json.dumps(summary, indent=2, default=str), overwrite=True)
    print(f"\n[INFO] DQ report written to {report_path}")
except Exception as e:
    print(f"[WARN] could not write DQ report: {e}")

print(f"\n[SUMMARY] {n_pass}/{len(results)} passed | {len(warns)} warning(s) | {len(hard_fails)} hard failure(s)")
if warns:
    print("[WARN] non-blocking warnings:")
    for r in warns:
        print(f"   - {r['type']} {r['column']} @ {r['table_fqn']}: {r['detail']}")

# COMMAND ----------

# ---- GATE: hard failures block the pipeline ----
if hard_fails:
    lines = "\n".join(
        f"   - {r['type']} {r['column']} @ {r['table_fqn']}: {r['detail']}" for r in hard_fails
    )
    raise AssertionError(
        f"DQ Gate FAILED: {len(hard_fails)} hard failure(s). Downstream blocked.\n"
        f"{lines}\n"
        f"Report: {REPORT_DIR}/dq_report_{RUN_ID}.json"
    )

print("[OK] DQ Gate passed — downstream may proceed.")
