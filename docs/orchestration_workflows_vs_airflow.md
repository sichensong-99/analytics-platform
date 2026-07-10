# Orchestration: Databricks Workflows vs Airflow

This platform's batch pipeline (`slice_1_daily`) runs on **Databricks Workflows** in
production. This document explains that choice, the conditions under which I'd move
to **Apache Airflow**, and a task-for-task concept mapping. A runnable Airflow demo
DAG that mirrors the production job 1:1 lives at `airflow/dags/slice_1_daily_dag.py`.

The point isn't "Workflows good, Airflow bad." Both are fine; the right answer is
situational, and being able to articulate *why* and *when* matters more than the tool.

---

## TL;DR

- **Production = Databricks Workflows.** The whole pipeline is Databricks-native
  (PySpark notebooks on one Lakehouse). A single-platform scheduler with native
  Unity Catalog / cluster / lineage integration means there is no second system to
  run, secure, and upgrade. For one Databricks-native DAG, Airflow is pure overhead.
- **I'd reach for Airflow** the moment orchestration spans *multiple* systems
  (Databricks + a separate warehouse + dbt + external REST APIs + reverse-ETL), or
  when an org has standardized on Airflow with a platform team behind it.
- The demo DAG proves I can author a non-trivial DAG and map three real production
  concerns to idiomatic Airflow primitives: **DQ-as-Gate → ShortCircuitOperator**,
  **single-node compute → Pool + priority_weight**, **per-task SLAs → execution_timeout / retries**.

---

## Why Databricks Workflows in production

1. **Single platform, zero extra infrastructure.** The transforms are Databricks
   notebooks; Workflows schedules them in the same workspace. No Airflow scheduler,
   metadata DB, executors, or webserver to provision, patch, monitor, and secure.
2. **Native integration.** Tasks bind directly to clusters and Unity Catalog;
   permissions, secrets, and table/column lineage are the platform's, not a
   bolted-on connection. Failure alerts and run history are built in.
3. **Jobs-as-code.** The job definition is exported and version-controlled as JSON
   and re-applied with `databricks jobs reset --json`, so the DAG is reproducible
   and reviewable without a second codebase. (Lesson learned the hard way: `jobs
   reset` is a *whole-replace*, so the exported JSON must be treated as the source
   of truth and re-pulled before edits.)
4. **Right-sized.** This is one pipeline on one platform. Adding Airflow would add a
   network hop and an entire system to operate for no functional gain.

This is a deliberate trade-off, not a default. Workflows' weaknesses (below) are
real; they just don't bite a single-platform pipeline.

## When I would switch to Airflow

- **Heterogeneous, multi-system orchestration** — e.g. extract from a REST API →
  load to Databricks → transform → push to Snowflake → trigger dbt → sync to a CRM.
  Airflow's provider ecosystem (one operator per system) is its core strength;
  Workflows is Databricks-centric.
- **Org standardization** — a central data-platform team running everything on
  Airflow, with shared connections, RBAC, and on-call already built around it.
- **Richer scheduling / control flow** — data-aware scheduling, sensors that wait on
  external events, dynamic task mapping, complex branching and backfill management.
- **Catchup / backfill of missed intervals** — Airflow models this natively
  (`catchup`, `data_interval`); Workflows does not.

A reasonable hybrid in a Databricks shop: keep transforms in Workflows and have
Airflow *invoke* them (`DatabricksRunNowOperator`) only to coordinate cross-system
steps — let each tool do what it's best at.

---

## Concept mapping

| Concern | Databricks Workflows | Airflow |
|---|---|---|
| Unit of work | task (`notebook_task`) | Operator (`PythonOperator`, `DatabricksSubmitRunOperator`, …) |
| Dependency edge | `depends_on` | `a >> b` / `set_upstream` |
| All-parents-succeed | `run_if: ALL_SUCCESS` | `trigger_rule="all_success"` (default) |
| Conditional skip / gate | gate notebook **raises** | **`ShortCircuitOperator`** (or `BranchPythonOperator`) |
| Schedule | `quartz_cron_expression` + `timezone_id` | `schedule` (cron) + `start_date` tz |
| One run at a time | `max_concurrent_runs=1` | `max_active_runs=1` |
| Missed-schedule backfill | (not supported) | `catchup` (set `False` to match) |
| Per-task timeout | `timeout_seconds` | `execution_timeout` |
| Retries | `max_retries` + `min_retry_interval_millis` | `retries` + `retry_delay` |
| Compute target | `existing_cluster_id` / job cluster | `DatabricksSubmitRunOperator(existing_cluster_id=… / new_cluster=…)` |
| Single-node contention | **structural**: add `depends_on` edges | **first-class**: `Pool` + `pool_slots` + `priority_weight` |
| Run-mode parameter | job widget (`full_refresh`, `lookback_days`) | DAG `params` / Airflow `Variable` / `--conf` |
| Failure alerts | `email_notifications.on_failure` | `on_failure_callback` / SLA-miss callbacks / `EmailOperator` |
| Definition-as-code | `databricks jobs reset --json` | the DAG `.py` file in `dags/` |

---

## Three mappings worth the detail

### 1. DQ-as-Gate → `ShortCircuitOperator`

The pipeline halts *before* bad data is published: a gate task runs the
YAML-driven data-quality suite, and if it fails, the downstream "publish" tasks
(`metric_refresh`, `success_digest`) do not run.

- **Workflows:** the `dq_gate` notebook raises on FAIL; because the publish tasks
  are `run_if: ALL_SUCCESS`, the raise propagates as task failure and they're skipped.
- **Airflow:** a `ShortCircuitOperator` returns `True`/`False`. On `False`, every
  downstream task is skipped. The nuance the demo highlights: `metric_refresh` has
  *two* parents (`dq_gate` and `page_view_gold`). `page_view_gold` is a sibling of
  the gate, not downstream of it, so it still runs — but `metric_refresh` is skipped
  because the gate short-circuited. That's the correct "don't publish on bad data"
  semantic, and it's why a ShortCircuit (skip-all-downstream) is the right operator
  rather than a branch.

### 2. Single-node compute → `Pool` + `priority_weight`

Constraint: no cluster-creation entitlement, so **all tasks share one i3.xlarge
node** (4 cores / ~30 GB). Heavy tasks running concurrently starve each other and
trip timeouts.

- **In Workflows** the only lever is *structural*: add `depends_on` edges to
  serialize the heavy independent branches behind the critical-path fact build.
  It works, but it encodes a *resource* constraint as a *data* dependency — the
  independent tasks aren't actually downstream of the fact; they're just made to
  wait so they don't compete. "Scheduling over scaling," but via a workaround.
- **In Airflow** there's a first-class primitive: a **Pool** with a fixed number of
  slots models the node's real capacity. Independent tasks stay dependency-honest
  (no fake edges) and the Pool still prevents them from oversubscribing the node;
  `priority_weight` (set high on the critical-path fact task) decides who gets a slot
  first under contention. The demo assigns every task to `single_node_pool` and caps
  the DAG with `max_active_tasks=2`.
- **The key point:** Workflows forced a structural workaround for a resource
  problem; Airflow expresses the same intent with a purpose-built concurrency control.
  Either way it's a *FinOps* decision — solve contention by scheduling, not by paying
  for more compute, under a fixed-compute constraint.

> `max_active_tasks` vs `Pool`: `max_active_tasks` caps concurrency for *this one DAG*
> and needs no setup — fine for a single demo. A `Pool` is shared across *all* DAGs,
> which is what you actually want when many pipelines contend for the same finite
> cluster. The demo shows both and explains the difference rather than picking blindly.

### 3. Per-task SLAs → `execution_timeout` / `retries` / `retry_delay`

The demo mirrors the live values exactly so the SLAs are real, not decorative:
`fact_orders_line` gets a 2-hour `execution_timeout` (it's the heavy join), the gate
gets `retries=0` (a gate should not auto-retry into the same bad data), light
control tasks get 10-minute timeouts, and `retry_delay` mirrors each task's
`min_retry_interval_millis`.

---

## Production wiring (no-op → real Databricks run)

The demo's tasks are no-op `PythonOperator`s so it runs anywhere with zero
dependencies. Swapping in real execution is a one-operator change per task — the
topology, pool, priority, and timeouts stay identical:

```python
from airflow.providers.databricks.operators.databricks import DatabricksSubmitRunOperator

fact_orders_line = DatabricksSubmitRunOperator(
    task_id="fact_orders_line",
    databricks_conn_id="databricks_default",     # host + token live in an Airflow Connection, never in code
    existing_cluster_id="<existing_cluster_id>", # the shared single-node cluster
    notebook_task={
        "notebook_path": "/Workspace/.../slice_1/04_build_fact_orders_line",
        "base_parameters": {"full_refresh": "false", "lookback_days": "3"},
    },
    pool="single_node_pool",
    priority_weight=10,
    weight_rule="absolute",
    execution_timeout=timedelta(hours=2),
)
```

Notes:
- **Auth** is an Airflow **Connection** (`databricks_default`), supplied via env or
  the secrets backend — credentials never appear in the DAG. This is exactly the
  integration that Workflows gives for free (the run already executes *inside* the
  workspace), which is the core "why Workflows in prod" argument made concrete: this
  is the *same* notebook run, now reached over a network hop from a second system.
- `base_parameters` map straight onto the job widgets the notebooks already read
  (`full_refresh`, `lookback_days`).

---

## Running the demo

Airflow is not supported natively on Windows — use **WSL2 (Ubuntu)** or Docker.

```bash
# WSL2 / Linux / macOS
python3 -m venv ~/airflow-venv && source ~/airflow-venv/bin/activate
pip install "apache-airflow==2.9.3"
export AIRFLOW_HOME=~/airflow
airflow standalone                  # prints an admin password; leave it running

# second shell, same venv + AIRFLOW_HOME:
airflow pools set single_node_pool 2 "Models the single i3.xlarge node"   # REQUIRED — every task is pooled
cp airflow/dags/slice_1_daily_dag.py "$AIRFLOW_HOME/dags/"
#   (from Windows paths, WSL sees the C: drive at /mnt/c/Users/...)
```

Open <http://localhost:8080>, unpause **`slice_1_daily_demo`**, hit **Trigger DAG**,
and watch the **Graph** view. To see the gate in action, set
`SIMULATE_DQ_FAILURE = True` in the DAG and re-trigger: `dq_gate` shows *success*
(the check ran) while `metric_refresh` and `success_digest` show *skipped*.

> Even without running it, the DAG file plus this document carry the value — the live
> green run is just for a README screenshot.

