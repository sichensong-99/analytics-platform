# Phase 4 Architecture Design Doc — Orchestration & DQ-as-Gate

> **Databricks Workflows DAG**: scheduled execution + retry/backoff + Slack/Email alerting + Data Quality as a pipeline gate + incremental loading.

---

## Document Control

| Field | Value |
|---|---|
| Author | Sia Song |
| Created | 2026-05-19 |
| Version | 1.0 |
| Status | 🟡 Pre-implementation (will start after Slice 1 completes) |
| Reviewers | Self; share with Databricks colleague + Leader after Slice 1 demo |
| Supersedes | None (first Phase 4 design doc) |
| Related Docs | `docs/architecture/slice_1_design.md`, `PROJECT_CONTEXT.md` (Decision 5 — Workflows over Airflow), `ROADMAP.md` (Phase 4 scope) |

### Changelog

| Version | Date | Author | Change |
|---|---|---|---|
| 1.0 | 2026-05-19 | Sia | Initial Phase 4 design covering DAG, triggers, DQ-as-gate, alerting, incremental loading. |

---

## 1. Executive Summary

### 1.1 What Phase 4 delivers

Phase 4 wraps the manually-runnable PySpark notebooks from Slice 1 into a
production-grade orchestrated pipeline using **Databricks Workflows**. The
deliverable is a scheduled, observable, retry-capable DAG that:

1. Refreshes dim tables daily (`dim_date` once; `dim_channel` on seed change;
   `dim_product` daily).
2. Rebuilds the slice 1 fact (`fact_orders_line`) daily on the slice 1 ETL window
   in the first iteration, then transitions to incremental append in iteration 2.
3. Runs DQ checks as a **gate** before declaring the run successful — failures
   block downstream metric refresh and alert the team.
4. Surfaces failures (and tier-promoted warnings) to Slack and email.

### 1.2 Why now, why this scope

After Slice 1 demo (Day 5), the manually-runnable notebooks are correct and
observable, but they need **someone to manually click run** every day. That
doesn't scale and isn't production-grade. Phase 4 turns the pipeline into a
self-driving system, which is also the key resume keyword cluster:

- **Orchestration / DAG design** (Databricks Workflows)
- **Idempotent pipelines / Retry with exponential backoff**
- **Data Quality as a gate** (pipeline integration of Track 3 DQ framework)
- **Observability** (failure alerting, run-level dashboards)
- **Incremental loading** (efficiency win, more realistic at scale)

### 1.3 Success criteria

A Phase 4 implementation is "done" when **all six** are true:

1. **Scheduled**: The DAG runs daily at 06:30 America/New_York without human
   intervention for 7 consecutive days.
2. **Idempotent**: Manual `Run now` produces identical output to scheduled runs;
   no duplicates, no orphan partitions.
3. **DQ-gated**: A deliberately-introduced data quality failure (e.g., null
   `order_line_id`) blocks the metric refresh task and surfaces in Slack within
   2 minutes of detection.
4. **Resilient**: Transient Databricks SQL warehouse hiccups are retried up to 3
   times with exponential backoff before the task is marked failed.
5. **Alerting verified**: A controlled failure injection produces a Slack
   notification with sufficient debug context (run URL, task name, error class,
   first failing assertion).
6. **Documented**: This design doc + a runbook (`docs/runbooks/phase4.md`) +
   Workflows config-as-code committed to git.

### 1.4 Timeline

| Day | Phase | Output |
|---|---|---|
| Day 1 | Configure Workflows job (UI initially, then export to JSON) | Job exists in dev workspace |
| Day 2 | Wire dim + fact notebooks as task dependencies | Linear DAG running end-to-end |
| Day 3 | Integrate DQ framework as a gate task | DQ failure blocks downstream |
| Day 4 | Slack/Email alerting + retry policy + failure injection tests | Alerts verified |
| Day 5 | Switch to incremental loading for `fact_orders_line` + runbook | Production-ready |

---

## 2. Background & Context

### 2.1 Where Slice 1 left off

By the end of Slice 1 demo (Day 5), four PySpark notebooks under
`databricks-notebooks/slice_1/` are runnable end-to-end:

- `01_build_dim_date.py` — loads `dim_date` from Parquet on Volume.
- `02_seed_dim_channel.py` — seeds `dim_channel` from version-controlled SQL.
- `03_build_dim_product.py` — builds `dim_product` from ERS + Shopify SKUs with
  graceful degradation (dual-schema-tolerant).
- `04_build_fact_orders_line.py` — Shopify ⨝ Triple Whale last-touch ⨝ dims,
  with DST-aware timezone normalization and multi-tier inline DQ checks.

These run manually today. Phase 4 turns them into a scheduled, observable system.

### 2.2 Locked decisions feeding into Phase 4

- **Decision 5**: Databricks Workflows over Airflow (deep Lakehouse integration,
  single-environment simplicity; revisit if multi-source heterogeneous needs
  emerge).
- **Decision 18**: Multi-tier DQ SLO (PASS/WARN/FAIL) with calibrated thresholds
  — implemented inline in notebook 04, will be wired through to alert routing.
- **Decision 13**: ETL temporally bounded (`>= 2025-07-01`), schema unbounded —
  this constrains incremental-load watermark logic.

### 2.3 Stakeholders

| Persona | Role | Phase 4 interaction |
|---|---|---|
| Sia | Pipeline owner | Builds, owns runbook, primary on-call |
| Databricks colleague | Platform admin | Grants Workflows job creation permission; consulted on cluster sizing |
| TW pipeline owner | Source data SLA | Coordinates if TW data is consistently late and shifts our daily trigger time |
| Leader | Observer | Subscribes to digest alerts; sees migration confidence increase as DQ checks run daily |

---

## 3. Goals & Non-goals

### 3.1 In scope (Phase 4)

- One Databricks Workflows job orchestrating dim + fact builds for Slice 1.
- Daily scheduled trigger (`0 30 6 * * ?` in America/New_York).
- Manual `Run now` for ad-hoc reruns.
- Task-level retry policy (3 retries, exponential backoff).
- DQ framework integration as a blocking gate after fact builds.
- Slack alerting on failure; daily digest email on success.
- Incremental load for `fact_orders_line` after the first full successful run.
- Workflows job config exported to JSON, committed to git as code.
- Runbook documenting common failure modes and recovery procedures.

### 3.2 Out of scope (deferred to Phase 4.5+)

- Streaming pipelines (Phase 4.5).
- Multi-DAG dependency graphs across slices (slice 2 will share the same DAG;
  more complex inter-slice dependencies wait until 3+ slices exist).
- Cross-environment deployment (dev → staging → prod) — single dev environment
  for now.
- Custom Databricks job monitoring dashboards (Workflows UI is sufficient;
  Phase 5 considers a tailored ops view).
- ML-driven anomaly detection on DQ trends (Phase 5+).
- Pager rotation / on-call schedule (currently single owner: Sia).

---

## 4. DAG Topology

### 4.1 Logical DAG

```
                    ┌─────────────────────────┐
                    │  Trigger: 06:30 NYT     │
                    │  daily / manual         │
                    └────────────┬────────────┘
                                 │
            ┌────────────────────┼────────────────────┐
            │                    │                    │
            ▼                    ▼                    ▼
   ┌────────────────┐  ┌─────────────────┐  ┌──────────────────┐
   │ 01_dim_date    │  │ 02_dim_channel  │  │ 03_dim_product   │
   │ (Parquet load) │  │ (seed SQL)      │  │ (ERS + Shopify)  │
   └────────┬───────┘  └────────┬────────┘  └────────┬─────────┘
            │                   │                    │
            └───────────────────┼────────────────────┘
                                ▼
                    ┌────────────────────────┐
                    │ 04_fact_orders_line    │
                    │ (Shopify ⨝ TW ⨝ dims)  │
                    │ inline multi-tier DQ   │
                    └───────────┬────────────┘
                                ▼
                    ┌────────────────────────┐
                    │ DQ Gate                │
                    │ (YAML configs run)     │
                    │ FAIL → block downstream│
                    └───────────┬────────────┘
                          on success
                                ▼
                    ┌────────────────────────┐
                    │ Metric Cache Refresh   │
                    │ (Phase 5 placeholder)  │
                    └───────────┬────────────┘
                                ▼
                    ┌────────────────────────┐
                    │ Success Digest         │
                    │ (Slack daily digest)   │
                    └────────────────────────┘
```

### 4.2 Task dependency rationale

- **Three dim builds run in parallel**: they share no data, parallelism saves
  ~30% of total wall-clock time, and Workflows handles concurrency natively.
- **Fact build depends on all three dims**: notebook 04 reads from all three
  dim tables for FK resolution; running it before any dim build will fail.
- **DQ Gate after fact build, before metric refresh**: a separate task (not
  inline in notebook 04) so DQ failures produce a distinct task-level failure
  with a clean error class, and downstream tasks can declare `depends_on_past=
  failure → skip` to avoid serving stale metrics.
- **Metric cache refresh after DQ**: in Phase 5 this becomes the Redis warm-up
  task; in Phase 4 it's a placeholder no-op task that we keep in the DAG so
  the topology doesn't change when Phase 5 lands.

### 4.3 Why DQ Gate is a separate task (not inline)

Notebook 04 already has inline multi-tier DQ checks (Decision 18). The separate
**DQ Gate task** runs the broader YAML-configured DQ framework (Track 3) and
covers:

| Inline (notebook 04) | DQ Gate (separate task) |
|---|---|
| Single-table runtime checks during ETL | Schema-level invariants across all 4 tables |
| Multi-tier with WARN/FAIL semantics | Boolean PASS/FAIL only (gate semantics) |
| Aborts the ETL itself | Aborts downstream tasks only — ETL output is preserved |
| Targets WARN signal in normal operation | Targets only FAIL conditions worth blocking metric refresh |

This separation is intentional: inline = developer-runtime safety net,
gate = production-pipeline integrity contract. They complement each other.

---

## 5. Trigger Strategy

### 5.1 Daily scheduled trigger

```
Cron       : 0 30 6 * * ?
Timezone   : America/New_York
Frequency  : Daily, 06:30 local
```

**Why 06:30 NYT**:

- Fivetran Shopify sync typically completes by ~05:00 NYT (verified during
  Slice 1 data validation period).
- Triple Whale custom pipeline completes around the same window.
- 06:30 leaves a 1.5-hour buffer for source-system tardiness without delaying
  the morning analyst review.
- Avoids overlap with other Databricks jobs in the workspace (verified by
  asking colleague about other scheduled jobs — currently quiet at this hour).

### 5.2 Manual `Run now`

Always available via Workflows UI for:

- Ad-hoc reruns after upstream data corrections.
- Backfills for historical date windows (manual override of ETL window).
- Demo runs while waiting for Day 2 morning slot.

### 5.3 Not in scope: file-arrival triggers

File-arrival (Auto Loader) triggers are Phase 4.5 (streaming module).
Slice 1 / Phase 4 stays on time-based triggers — simpler, sufficient.

---

## 6. Failure Strategy

### 6.1 Retry policy (per task)

```yaml
max_retries          : 3
min_retry_interval   : 60s
retry_backoff        : exponential   # 60s → 180s → 540s
retry_on_timeout     : true
```

**Rationale**:

| Failure class | Expected? | Retry behavior |
|---|---|---|
| SQL warehouse transient connection error | Yes | Retry handles |
| Spark cluster startup race | Yes | Retry handles |
| Source table not yet refreshed (Fivetran late) | Sometimes | Retries usually clear; if not, alert |
| Code bug (assertion error in notebook) | Never | Retry is wasteful but harmless; alert fires after 3rd retry |
| DQ failure (genuine data issue) | Hopefully no | Should fail fast; see §7.3 |

### 6.2 Retry exclusions

DQ Gate task does **not** retry. A DQ failure is by definition a data
integrity statement — retrying will produce the same result and only delay
the alert. Configured explicitly:

```yaml
dq_gate_task:
  max_retries: 0
```

### 6.3 Failure escalation

After max retries exhausted:

1. Task marked `FAILED` in Workflows.
2. Workflow marked `FAILED`.
3. Slack webhook fires (§8.1).
4. Downstream tasks (metric refresh, success digest) skip via
   `depends_on_past = success_or_skipped`.
5. Next day's run starts fresh; no auto-resume from prior failure (intentional
   — we want a human to confirm yesterday's failure was understood before
   another run goes out).

---

## 7. DQ-as-Gate Pattern ⭐

This is Phase 4's signature engineering pattern and the highest-leverage resume
keyword.

### 7.1 The pattern

```
ETL produces data ──► DQ Gate runs ──► metrics consume data
                          │
                       fails?
                          │
                          ▼
                downstream blocked
                alert raised
                ETL output remains
                (debuggable, not deleted)
```

### 7.2 Implementation

A dedicated Workflows task runs after `04_build_fact_orders_line.py`:

```python
# databricks-notebooks/slice_1/dq_gate.py

from data_quality.runner import DQRunner

# Load all 4 YAML configs for slice 1 tables
dq_configs = [
    "metrics-service/data_quality/configs/slice_1_dim_date.yaml",
    "metrics-service/data_quality/configs/slice_1_dim_channel.yaml",
    "metrics-service/data_quality/configs/slice_1_dim_product.yaml",
    "metrics-service/data_quality/configs/slice_1_fact_orders_line.yaml",
]

runner = DQRunner(configs=dq_configs)
results = runner.run_all()

# Write report (console + JSON)
runner.write_console_report(results)
runner.write_json_report(results, "/tmp/dq_report_{{run_id}}.json")

# Gate semantics: ANY hard-fail check halts the pipeline
if results.has_failures():
    raise AssertionError(
        f"DQ Gate FAILED: {results.failure_count} hard failures. "
        f"See report: dbfs:/tmp/dq_report_{{run_id}}.json"
    )

# Soft warnings are logged but don't halt
if results.has_warnings():
    print(f"[WARN] DQ Gate produced {results.warning_count} warnings; pipeline continues.")
```

### 7.3 Hard fail vs soft warn taxonomy

Each YAML-configured check declares its severity:

```yaml
# example slice_1_fact_orders_line.yaml
checks:
  - type: not_null
    column: order_line_id
    severity: fail        # any null → block downstream

  - type: unique
    column: order_line_id
    severity: fail        # any duplicate → block downstream

  - type: freshness
    column: _ingest_at
    max_age_hours: 36
    severity: warn        # stale data is concerning but not blocking
```

**Hard fail (severity: fail)** examples:

- PK null or duplicate (data integrity broken).
- FK referential integrity violation beyond multi-tier FAIL threshold.
- Total row count outside hard bounds (likely a catastrophic upstream issue).

**Soft warn (severity: warn)** examples:

- Freshness exceeded (data slightly stale, still serve).
- Unresolved key % in WARN tier (legitimate variation).

### 7.4 Why this is resume gold

- It demonstrates **separation of correctness gates from observability signals**.
- It shows **data quality as a first-class pipeline citizen**, not an afterthought.
- It mirrors the SRE concept of **error budget** — WARN consumes budget, FAIL
  exhausts it.

---

## 8. Alerting

### 8.1 Slack on failure

Slack webhook fires on any task FAIL after retries are exhausted.

```python
# databricks-notebooks/slice_1/util/alert.py

import requests
import os

def slack_alert(workflow_run_url: str, task_name: str, error_summary: str):
    webhook = os.environ["SLACK_WEBHOOK_ANALYTICS_ALERTS"]
    payload = {
        "blocks": [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "🚨 Analytics Pipeline Failure"}
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Task:*\n{task_name}"},
                    {"type": "mrkdwn", "text": f"*Run:*\n<{workflow_run_url}|Open>"}
                ]
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Error:*\n```{error_summary[:500]}```"}
            }
        ]
    }
    requests.post(webhook, json=payload, timeout=5)
```

Triggered by Workflows native "on failure" task notification:

```yaml
email_notifications:
  on_failure: [sia.song@32degrees.com]
webhook_notifications:
  on_failure:
    - id: slack_analytics_alerts
```

### 8.2 Daily success digest

A separate "success digest" task runs at the end of a successful DAG and posts
a brief summary to Slack:

```
✅ Analytics Pipeline OK — 2026-05-20
   • fact_orders_line: 10,234,567 rows (+12,345 vs yesterday)
   • DQ: 18 checks passed, 0 warnings
   • Runtime: 23 min 14 sec
   • Yesterday's anomalies: none
```

Why bother on success: gives Leader passive visibility ("the platform is
running") and surfaces gradual trends (row counts, runtime growth) before
they become incidents.

### 8.3 Severity routing (future)

Phase 4 starts with one Slack channel for all alerts. Future evolution
(Phase 5+) routes by severity:

- DQ FAIL → high-priority channel + paging
- DQ WARN → digest only
- ETL task failure → engineering channel

---

## 9. Incremental vs Full Rebuild ⭐

### 9.1 First iteration: full rebuild

For the first 1-2 weeks after Slice 1 demo, the fact table is **fully
rebuilt** each daily run (drop and recreate). This is what notebook 04 does
today.

**Pros**:

- Simple, no watermark state to maintain.
- Self-healing: any historical correction in upstream Shopify/TW
  automatically flows through.
- Day-over-day reproducibility (a re-run on the same date produces an
  identical table to ±0 rows).

**Cons**:

- ~3-5 min per million rows scanned; grows linearly with the ETL window.
- Wasteful at 90+ days.

### 9.2 Second iteration: incremental append

After full-rebuild operation is verified stable, switch to incremental:

```python
# Pseudocode for incremental
last_ingest = spark.sql(
    "SELECT MAX(_ingest_at) FROM analytics_platform_32degrees.fact_orders_line"
).first()[0]

new_orders = spark.table(SHOPIFY_ORDER) \
    .filter(F.col("updated_at") > last_ingest) \
    .filter(F.col("processed_at") >= ETL_START_DATE)

# ... compose fact rows for new orders only ...

# Merge into target instead of overwrite
new_fact_rows.write \
    .format("delta") \
    .mode("append") \
    .saveAsTable(FULL_TARGET)
```

Plus a periodic compaction/optimize:

```python
spark.sql("OPTIMIZE fact_orders_line ZORDER BY (channel_key, product_key)")
spark.sql("VACUUM fact_orders_line RETAIN 168 HOURS")  # 7 days
```

### 9.3 Late-arriving data strategy

Incremental loading must handle late-arriving order updates from Shopify
(refunds, cancellations, status changes). Strategy:

- Use Shopify `updated_at` (not `created_at`) as the watermark column —
  catches any row that changed.
- Use Delta `MERGE INTO` on `order_line_id` PK for updates rather than blind
  append (avoids duplicates).
- Set watermark lookback to 2 days on each run (`updated_at > last_run - 2 days`)
  to catch late updates that arrived after the previous watermark advanced.

### 9.4 Why staged migration (full → incremental)

Going incremental on day 1 mixes two complexity sources (orchestration +
incremental load) and makes Day 5 of Phase 4 hard to debug. Staged migration
isolates concerns and is the classic "ship slow, then optimize" pattern.

Resume framing: "Designed staged migration from full rebuild to incremental
load with `updated_at` watermark and 2-day lookback to handle late-arriving
Shopify order updates, balancing simplicity with cost."

---

## 10. Idempotency & Recovery

### 10.1 Idempotency primitives

| Object | Idempotency mechanism |
|---|---|
| `dim_date` | `mode("overwrite")` — same Parquet input → same output |
| `dim_channel` | TRUNCATE + INSERT (versioned seed SQL) |
| `dim_product` | `mode("overwrite")` — full SCD1 rebuild from same source |
| `fact_orders_line` (full mode) | `mode("overwrite")` partitioned by `date_key` |
| `fact_orders_line` (incremental mode) | `MERGE INTO` on PK — re-running same window produces same result |
| DQ gate | Read-only; trivially idempotent |

### 10.2 Recovery procedures

**Scenario 1: Single task failed, others succeeded**
Restart the failed task only via Workflows UI. Upstream outputs are unchanged.

**Scenario 2: Whole DAG failed mid-way**
Manual `Run now` from the top. Idempotency guarantees no corruption.

**Scenario 3: Data correction needed for a past date**
Set `RUN_MODE = "full"` in notebook 04 and trigger a manual run. Full rebuild
overwrites the affected partitions.

**Scenario 4: Catastrophic schema change**
Use Delta Time Travel:
```sql
DESCRIBE HISTORY analytics_platform_32degrees.fact_orders_line;
RESTORE TABLE analytics_platform_32degrees.fact_orders_line TO VERSION AS OF <n>;
```

### 10.3 Run-id traceability

Every notebook logs its Workflows run ID at the start:

```python
run_id = dbutils.notebook.entry_point.getDbutils().notebook().getContext() \
    .toJson()  # extract run_id from JSON
print(f"[INFO] Workflows run_id: {run_id}")
```

DQ reports are written with `run_id` suffix:
`/tmp/dq_report_<run_id>.json`. Enables post-hoc forensic analysis.

---

## 11. Configuration as Code

### 11.1 Workflows job as JSON

The Workflows job, once configured in the UI, is exported to JSON and
committed to git:

```
databricks-workflows/
└── slice_1_daily.json
```

This enables:

- Code review of pipeline structure (PRs)
- Bootstrapping a new environment by importing JSON
- Drift detection (compare deployed JSON vs git JSON)

### 11.2 Deployment

Initial deployment is manual via the Workflows UI. Future iteration (Phase 6
or a separate dev-ops slice) could automate via Databricks CLI:

```bash
databricks jobs reset --job-id <id> --json @databricks-workflows/slice_1_daily.json
```

### 11.3 Sensitive config

Slack webhook URL, email recipients: stored in Databricks Secrets (`scope:
analytics-platform`, `key: slack-webhook-url`). Never in JSON or notebooks.

---

## 12. Code Templates

### 12.1 DQ Gate notebook scaffold

(See §7.2 above for the full template.)

### 12.2 Slack alert helper

(See §8.1 above.)

### 12.3 Success digest task

```python
# databricks-notebooks/slice_1/success_digest.py

from datetime import datetime
from data_quality.runner import DQRunner

# Yesterday's vs today's row count
today_count = spark.table("fact_orders_line").count()
yesterday_count = spark.sql("""
    SELECT count_estimate FROM ops.pipeline_history
    WHERE run_date = current_date() - INTERVAL 1 DAY
""").first()[0] or today_count

delta = today_count - yesterday_count

# Latest DQ summary (from last DQ gate run)
dq_summary = "18 checks passed, 0 warnings"  # placeholder; pull from DQ report

# Post to Slack
slack_digest(
    today=datetime.now().strftime("%Y-%m-%d"),
    row_count=today_count,
    delta=delta,
    dq_summary=dq_summary,
    runtime="..."
)

# Persist today's count for tomorrow's delta calc
spark.sql(f"""
    INSERT INTO ops.pipeline_history VALUES (
        current_date(),
        {today_count},
        '{dq_summary}'
    )
""")
```

### 12.4 Workflows JSON skeleton

```json
{
  "name": "slice_1_daily",
  "max_concurrent_runs": 1,
  "schedule": {
    "quartz_cron_expression": "0 30 6 * * ?",
    "timezone_id": "America/New_York",
    "pause_status": "UNPAUSED"
  },
  "tasks": [
    {
      "task_key": "dim_date",
      "notebook_task": {"notebook_path": "/Repos/.../slice_1/01_build_dim_date"},
      "max_retries": 3,
      "min_retry_interval_millis": 60000,
      "retry_on_timeout": true
    },
    {
      "task_key": "dim_channel",
      "notebook_task": {"notebook_path": "/Repos/.../slice_1/02_seed_dim_channel"},
      "max_retries": 3
    },
    {
      "task_key": "dim_product",
      "notebook_task": {"notebook_path": "/Repos/.../slice_1/03_build_dim_product"},
      "max_retries": 3
    },
    {
      "task_key": "fact_orders_line",
      "depends_on": [
        {"task_key": "dim_date"},
        {"task_key": "dim_channel"},
        {"task_key": "dim_product"}
      ],
      "notebook_task": {"notebook_path": "/Repos/.../slice_1/04_build_fact_orders_line"},
      "max_retries": 3
    },
    {
      "task_key": "dq_gate",
      "depends_on": [{"task_key": "fact_orders_line"}],
      "notebook_task": {"notebook_path": "/Repos/.../slice_1/dq_gate"},
      "max_retries": 0
    },
    {
      "task_key": "metric_refresh",
      "depends_on": [{"task_key": "dq_gate"}],
      "notebook_task": {"notebook_path": "/Repos/.../slice_1/metric_refresh_placeholder"},
      "max_retries": 2
    },
    {
      "task_key": "success_digest",
      "depends_on": [{"task_key": "metric_refresh"}],
      "notebook_task": {"notebook_path": "/Repos/.../slice_1/success_digest"},
      "max_retries": 1
    }
  ],
  "email_notifications": {
    "on_failure": ["sia.song@32degrees.com"]
  },
  "webhook_notifications": {
    "on_failure": [{"id": "slack_analytics_alerts"}]
  }
}
```

---

## 13. Workflows vs Airflow Trade-off

This is the answer to the canonical interview question: "Why didn't you use
Airflow?" Preparing it here so the answer is consistent and reasoned.

| Dimension | Databricks Workflows | Apache Airflow |
|---|---|---|
| Deployment & ops overhead | Zero — managed by Databricks | Significant — must run scheduler + workers |
| Integration with Spark / Delta | Native; passes notebooks directly | Requires `DatabricksSubmitRunOperator` or similar wrapper |
| Cross-platform orchestration (DB + S3 + APIs + Snowflake) | Limited beyond Databricks | Strong — was designed for this |
| Dynamic DAG generation | Limited (config-as-code helps) | Excellent (Python DAG files) |
| UI / observability | Built into Databricks workspace | Standalone web UI |
| Cost | Included in DBU usage | Self-hosted infra cost (or Astronomer Cloud) |
| Lock-in | Higher (Databricks-specific config) | Lower (portable to other clouds) |
| Resume keyword recognition | Growing (~30% of postings) | Industry standard (~80% of postings) |

### Decision rationale (for this project)

- **All compute is in Databricks**: pipeline tasks are PySpark notebooks. Airflow's
  cross-platform strength provides no value here.
- **Single owner, single environment**: no team rotation or multi-env complexity
  that Airflow's portability would help with.
- **Time budget**: Phase 4 is 1 week. Airflow setup alone consumes most of that.
- **Resume coverage**: "Databricks Workflows" is recognized at the keyword level
  by data engineering recruiters; the underlying skill (DAG design, retry
  policy, alerting) transfers verbatim to Airflow.

### When this decision would flip

- Multi-source pipelines (Databricks + Snowflake + external APIs).
- Multi-team / multi-environment with promotion workflows.
- Need for dynamic DAGs (e.g., one DAG per customer).

This nuance is the heart of the interview answer — engineers who can articulate
**when their decision flips** are differentiated from those who memorize the
"why I chose X" without context sensitivity.

---

## 14. Risks & Mitigations

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R1 | Fivetran sync runs late, fact build misses today's orders | Medium | Low (next day catches up) | Schedule at 06:30, well after typical sync; lookback window in incremental mode |
| R2 | Slack webhook silently fails (DNS, rate limit) | Low | Medium (silent failures) | Add fallback email notification; periodic webhook health check |
| R3 | DQ Gate becomes flaky (false positives erode trust) | Medium | High (alert fatigue → ignored alerts) | Multi-tier with WARN tier absorbing normal variation; periodically review and retune |
| R4 | Workflows JSON drifts from git as quick UI edits accumulate | Medium | Low-medium (config sprawl) | Weekly export-and-diff process; PR-only changes ideal but enforce with weekly audit |
| R5 | Incremental loading misses an updated order due to watermark misconfig | Low | Medium (silent data drift) | 2-day lookback buffer; weekly reconciliation against full rebuild to detect drift |
| R6 | Single owner (Sia) — bus factor of 1 | Medium | High | Comprehensive runbook (`docs/runbooks/phase4.md`); colleague onboarded as backup-on-call |

---

## 15. Estimated Implementation Plan

5-day plan, executed after Slice 1 demo.

| Day | Tasks | Output |
|---|---|---|
| **Day 1** | Configure Workflows job in UI (linear DAG: dim → fact); verify each task runs; export to JSON; commit | `databricks-workflows/slice_1_daily.json` v1 |
| **Day 2** | Add retry policy; add Slack webhook secret; trigger a deliberate failure to verify Slack alert fires | Alert verified |
| **Day 3** | Implement DQ Gate task; integrate Track 3 DQ framework; verify FAIL blocks downstream | DQ Gate live |
| **Day 4** | Add success digest task; deploy daily schedule; observe 1 full successful run | First scheduled run complete |
| **Day 5** | Migrate `fact_orders_line` to incremental mode; weekly reconciliation against full rebuild to verify parity; write runbook | Phase 4 production-ready |

---

## 16. Open Questions

These need answers before Phase 4 implementation starts:

1. **Slack webhook URL**: Does the analytics team have an existing Slack channel
   we can post to, or do we create `#analytics-platform-alerts`?
   *Owner*: Sia coordinates with team.

2. **Email distribution list**: Personal email (`sia.song@`) or a team alias
   (`analytics-eng@`)? Latter is more resilient to PTO.
   *Owner*: Sia decides; team alias preferred.

3. **Workflows job ownership**: Set to Sia personally, or to a service principal?
   Service principal is more resilient to employee turnover but requires admin
   setup.
   *Owner*: Discuss with Databricks colleague in Day 1.

4. **Cluster choice**: Reuse the existing all-purpose cluster, or create a
   job-specific cluster for cost optimization (auto-scales down between runs)?
   *Owner*: Default to job cluster for cost; benchmark on Day 1.

---

## 17. Appendix

### A. Glossary

- **DAG**: Directed Acyclic Graph — the data structure underlying Workflows /
  Airflow pipeline definitions.
- **Idempotent**: A pipeline is idempotent if running it twice produces the
  same output as running it once.
- **Watermark**: In incremental ETL, the timestamp dividing "already processed"
  rows from "to be processed" rows.
- **DQ Gate**: A pipeline task that fails if data quality checks fail, blocking
  downstream tasks.
- **DQ tier (WARN/FAIL)**: From Decision 18 — a multi-level severity for
  quality checks distinguishing "operational signal" from "integrity breach".

### B. References

- `PROJECT_CONTEXT.md` §5 Decision 5 (Workflows over Airflow), 13 (ETL window),
  18 (Multi-tier DQ)
- `docs/architecture/slice_1_design.md` §10 (DQ Plan)
- `databricks-notebooks/slice_1/*.py` — the notebooks orchestrated by this DAG
- `metrics-service/data_quality/` — Track 3 DQ framework (referenced by Gate)
- Databricks Workflows docs: <https://docs.databricks.com/workflows>

### C. Resume notes

This design contributes the following resume points (in priority order):

1. **"Authored Phase 4 orchestration design document for daily DAG, DQ-as-gate
   integration, multi-tier alerting, and staged incremental loading migration
   on Databricks Workflows."**
2. **"Designed DQ-as-Gate pattern separating runtime safety checks (inline,
   multi-tier with WARN/FAIL semantics) from production-pipeline integrity
   contracts (separate gate task with PASS/FAIL semantics) — complementary
   not redundant."**
3. **"Architected staged migration from full rebuild to incremental load on
   `fact_orders_line` with `updated_at` watermark + 2-day lookback to capture
   late-arriving Shopify order updates."**
4. **"Configured Slack webhook + email alerting with structured payload
   (run URL, task name, failing assertion class) and parallel daily success
   digest for passive Leader visibility."**
5. **"Articulated Databricks Workflows vs Airflow trade-off with explicit
   conditions under which the decision would flip (multi-source, multi-env,
   dynamic DAGs), demonstrating context sensitivity beyond keyword matching."**

---

*End of Phase 4 Architecture Design Doc v1.0.*
