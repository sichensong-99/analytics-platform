"""
slice_1_daily — Airflow demo DAG (1:1 topology mirror of the Databricks Workflows job)
=======================================================================================

WHAT THIS IS
------------
A *sample / demo* Airflow DAG that mirrors the production ``slice_1_daily``
Databricks Workflows job task-for-task and edge-for-edge. Production orchestration
for this platform IS and STAYS Databricks Workflows — see
``docs/orchestration_workflows_vs_airflow.md`` for the why, the when-to-switch,
and the full concept mapping.

This DAG exists to:
  1. Author a real, non-trivial DAG (11 tasks, fan-in / fan-out / parallel branch).
  2. Map three production concerns to their idiomatic Airflow primitives:
       - DQ-as-Gate           -> ShortCircuitOperator
       - single-node compute  -> Pool + max_active_tasks + priority_weight
       - per-task SLA/retries  -> execution_timeout / retries / retry_delay
  3. Run locally with ``airflow standalone`` and ZERO Databricks/cloud dependency:
     every task is a no-op PythonOperator that just logs + simulates work.

It is NOT wired to Databricks. The comparison doc shows the one-operator swap from a
no-op PythonOperator to a DatabricksSubmitRunOperator for real execution.

QUICKSTART (local, ~2 min)
--------------------------
  # Airflow is not supported natively on Windows — run inside WSL2 (Ubuntu) or Docker.
  python3 -m venv ~/airflow-venv && source ~/airflow-venv/bin/activate
  pip install "apache-airflow==2.9.3"
  export AIRFLOW_HOME=~/airflow
  airflow standalone                         # starts scheduler + webserver; note the printed admin password

  # in a second shell (same venv + same AIRFLOW_HOME):
  airflow pools set single_node_pool 2 "Models the single i3.xlarge node"   # REQUIRED: every task is pooled
  cp slice_1_daily_dag.py "$AIRFLOW_HOME/dags/"

  # browser -> http://localhost:8080 -> unpause 'slice_1_daily_demo' -> Trigger DAG -> watch the Graph view.

  # To watch the DQ gate short-circuit the publish branch:
  #   set SIMULATE_DQ_FAILURE = True below, refresh, re-trigger ->
  #   dq_gate shows 'success' (the check ran) but metric_refresh + success_digest show 'skipped'.

REAL TOPOLOGY MIRRORED (from `databricks jobs get <job_id>`)
-------------------------------------------------------------------
  build_dimensions:                                  (3 independent roots)
      dim_date, dim_channel, dim_product
  fact_orders_line  <- dim_date, dim_channel, dim_product
  dq_gate           <- fact_orders_line              (ShortCircuit gate)
  ga4_ingest                                         (independent root, parallel)
  page_view_gold    <- ga4_ingest, fact_orders_line
  metric_refresh    <- dq_gate, page_view_gold
  success_digest    <- metric_refresh
  cohort_build                                       (independent leaf)
  lineage_edges                                      (independent leaf)
"""

from __future__ import annotations

import time
from datetime import timedelta

import pendulum
from airflow.models.dag import DAG
from airflow.operators.python import PythonOperator, ShortCircuitOperator
from airflow.utils.task_group import TaskGroup

# ---------------------------------------------------------------------------
# Demo knobs
# ---------------------------------------------------------------------------
SIMULATED_WORK_SECONDS = 2          # set 0 for an instant run; >0 makes the Graph view legible
SIMULATE_DQ_FAILURE = False         # flip True to watch dq_gate short-circuit the publish branch
SINGLE_NODE_POOL = "single_node_pool"   # create with: airflow pools set single_node_pool 2 "..."

ET = pendulum.timezone("America/New_York")


# ---------------------------------------------------------------------------
# No-op task body. In production each of these is a Databricks notebook run; here
# it just logs + sleeps so the demo is self-contained and Databricks-free.
# ---------------------------------------------------------------------------
def _run_step(label: str, **context) -> None:
    print(f"[demo] START  {label}  (run {context['run_id']})")
    if SIMULATED_WORK_SECONDS:
        time.sleep(SIMULATED_WORK_SECONDS)
    print(f"[demo] DONE   {label}")


def _dq_gate_check(**context) -> bool:
    """
    DQ-as-Gate, Airflow idiom.

    Production analogue: the `dq_gate` notebook runs the YAML-driven DQ suite and
    RAISES on FAIL; with run_if=ALL_SUCCESS on the downstream tasks, a raise blocks
    publish. A ShortCircuitOperator is the native Airflow equivalent: returning
    False skips EVERY downstream task, so bad data never reaches metric_refresh —
    even though page_view_gold (a sibling, not downstream of the gate) still ran.
    """
    passed = not SIMULATE_DQ_FAILURE
    print(f"[demo] DQ gate evaluated -> {'PASS' if passed else 'FAIL (short-circuit)'}")
    return passed


# Common per-task settings; these mirror the production retries/timeouts and are
# overridden per task below where the live job differs.
default_args = {
    "owner": "analytics-platform",
    "retries": 2,                                  # most tasks: max_retries=2 in Workflows
    "retry_delay": timedelta(seconds=120),         # min_retry_interval_millis=120000
    "execution_timeout": timedelta(minutes=30),    # timeout_seconds=1800 (default)
}


def _pyop(task_id: str, *, priority_weight: int = 1, **overrides) -> PythonOperator:
    """A pooled no-op PythonOperator with explicit, absolute slot priority."""
    return PythonOperator(
        task_id=task_id,
        python_callable=_run_step,
        op_kwargs={"label": task_id},
        pool=SINGLE_NODE_POOL,             # all tasks share the one node's capacity
        priority_weight=priority_weight,
        weight_rule="absolute",            # deterministic priority (not summed over downstream)
        **overrides,
    )


with DAG(
    dag_id="slice_1_daily_demo",
    description="Demo mirror of the production Databricks Workflows job 'slice_1_daily'",
    schedule="30 6 * * *",                 # Quartz '0 30 6 * * ?' -> standard cron '30 6 * * *'
    start_date=pendulum.datetime(2026, 6, 1, tz=ET),
    catchup=False,                         # Workflows does not backfill missed schedules
    max_active_runs=1,                     # Workflows max_concurrent_runs=1
    max_active_tasks=2,                    # single-node ceiling (belt-and-suspenders with the pool)
    default_args=default_args,
    tags=["demo", "slice_1", "databricks-mirror"],
    doc_md=__doc__,
) as dag:

    # --- ODS / dimension layer: 3 independent roots, grouped for readability ----
    with TaskGroup(group_id="build_dimensions") as build_dimensions:
        dim_date = _pyop("dim_date", priority_weight=3)
        dim_channel = _pyop("dim_channel", priority_weight=3)
        dim_product = _pyop("dim_product", priority_weight=3)

    # --- core fact (critical path): highest priority on the shared node ---------
    fact_orders_line = _pyop(
        "fact_orders_line",
        priority_weight=10,
        execution_timeout=timedelta(hours=2),       # timeout_seconds=7200
    )

    # --- DQ gate: ShortCircuit. retries=0 in prod (a gate should not auto-retry) -
    dq_gate = ShortCircuitOperator(
        task_id="dq_gate",
        python_callable=_dq_gate_check,
        pool=SINGLE_NODE_POOL,
        priority_weight=8,
        weight_rule="absolute",
        retries=0,
        execution_timeout=timedelta(minutes=30),
        # ignore_downstream_trigger_rules defaults to True: on a False return, ALL
        # downstream tasks are skipped, so metric_refresh is skipped even though its
        # other parent (page_view_gold) succeeded — exactly the "halt before bad
        # data publishes" semantic.
    )

    # --- GA4 ingest: independent root, runs in parallel with the dims/fact -------
    ga4_ingest = _pyop(
        "ga4_ingest",
        priority_weight=4,
        execution_timeout=timedelta(hours=1),       # timeout_seconds=3600
    )

    # --- page_view gold: needs GA4 silver + the order fact ----------------------
    page_view_gold = _pyop(
        "page_view_gold",
        priority_weight=5,
        execution_timeout=timedelta(hours=1),       # timeout_seconds=3600
    )

    # --- publish branch ---------------------------------------------------------
    metric_refresh = _pyop(
        "metric_refresh",
        priority_weight=6,
        execution_timeout=timedelta(minutes=10),    # timeout_seconds=600
        retry_delay=timedelta(seconds=60),
    )
    success_digest = _pyop(
        "success_digest",
        priority_weight=6,
        retries=1,
        execution_timeout=timedelta(minutes=10),    # timeout_seconds=600
        retry_delay=timedelta(seconds=60),
    )

    # --- independent side branches (no upstream, nothing depends on them) -------
    # In the LIVE job these carry NO depends_on. The single-node contention they
    # create is handled here by the Pool (see the comparison doc) rather than by
    # adding artificial dependency edges.
    cohort_build = _pyop(
        "cohort_build",
        priority_weight=2,
        retries=1,
        retry_delay=timedelta(seconds=60),
    )
    lineage_edges = _pyop(
        "lineage_edges",
        priority_weight=2,
        retries=1,
        execution_timeout=timedelta(minutes=10),    # timeout_seconds=600
        retry_delay=timedelta(seconds=60),
    )

    # ---------------------------------------------------------------------------
    # Dependency wiring — edge-for-edge with the Workflows job
    # ---------------------------------------------------------------------------
    build_dimensions >> fact_orders_line
    fact_orders_line >> dq_gate
    [ga4_ingest, fact_orders_line] >> page_view_gold
    [dq_gate, page_view_gold] >> metric_refresh
    metric_refresh >> success_digest
    # cohort_build and lineage_edges intentionally have no edges (independent).
