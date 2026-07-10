# Runbook — Slice 1 Daily Pipeline (`slice_1_daily`)

Operational guide for the Slice-1 sales-by-channel pipeline. Audience: whoever is
on call for the analytics platform (currently Sia). Keep this current as the
pipeline evolves.

---

## 1. What this pipeline produces

A daily-refreshed star schema for the **Style-by-channel quantity** use case.

| Output table | Grain | Notes |
|---|---|---|
| `analytics_catalog.analytics_platform.dim_date` | one row per calendar day | ISO year/week/day |
| `…dim_channel` | one row per TW channel source | seed table; `channel_key = 0` = Unknown |
| `…dim_product` | one row per SKU | `product_key = 0` = Unknown member |
| `…fact_orders_line` | **one row per Shopify order line** | natural key `shopify_line_id`; sales fact joined with Triple Whale last-touch attribution |
| `…pipeline_run_history` | one row per successful run-day | row-count history for the success digest |

**Sources**: Shopify (via Fivetran) for orders/lines; Triple Whale (federated
catalog `federated_catalog.triple_whale`) for attribution; ERS product
master (monthly CSV upload) for dim_product. TW data exists from 2025-07-01 only.

**Trust gate**: new platform reconciles to within **−1.51%** of legacy Panoply on
the validation window (**ISO week 28 of 2025**), inside the ±2% trust threshold.

---

## 2. DAG topology

```
dim_date ─┐
dim_channel ─┼─→ fact_orders_line ─→ dq_gate ─→ metric_refresh ─→ success_digest
dim_product ─┘
```

- The three dimensions build **in parallel**, then fan **in** to the fact.
- `dq_gate` is a **hard quality gate**: a hard failure raises an exception, the
  task fails, and all downstream tasks are **skipped** (fail-closed) — bad data
  never reaches consumers. The fact table is **not** deleted on gate failure, so
  it stays debuggable.
- `metric_refresh` is currently a **no-op placeholder** (becomes the Redis cache
  warm-up in Phase 5).
- `success_digest` records the day's row count and prints a health summary
  (posts to Slack only if the webhook secret is configured).

---

## 3. Schedule & compute

- **Schedule**: daily at **06:30 America/New_York** (`0 30 6 * * ?`), DST-aware.
- **Compute**: a governed **single-user Personal Compute** cluster (classic),
  referenced by all tasks via `existing_cluster_id`. Classic compute is required
  because notebook 04 uses `.cache()` (unsupported on serverless); an ephemeral
  job cluster is not used because the workspace disables the cluster-creation
  entitlement. The cluster auto-terminates after each run (idle cost bounded); a
  scheduled run starts it automatically, adding a couple of minutes.
- **Notifications**: email on failure to `sia.song@example.com`.
- **Retries**: dim/fact tasks retry up to 2× with a 2-minute backoff; `dq_gate`
  does **not** retry (a real data failure should not be retried — fix the data).

---

## 4. The DQ gate

- **What it checks**: the same YAML check specs under `slice_1/dq_configs/`
  (`dim_date`, `dim_channel`, `dim_product`, `fact_orders_line`), executed in
  **Spark** so they scale to the ~10M-row fact.
- **Severity model**:
  - `not_null` / `unique` → **FAIL** (PK / FK integrity broken → blocks pipeline)
  - `range` / `freshness` → **WARN** (domain sanity / staleness → logged, non-blocking)
  - any single check can override with a `severity:` key in its YAML spec.
- **Report**: a run-id-suffixed JSON report is written to `dbfs:/tmp/dq_reports/`
  for every run (forensic traceability).
- **Expected WARNs**: `quantity > 100` or `pre_tax_price > 10000` on a line
  (large B2B orders). These are surfaced, not blocked — that's intended.

---

## 5. Failure response

First: open the failed run in **Workflows → `slice_1_daily` → the red run**, click
the failed task, read the last ~20 lines of **Output**.

| Failed task | Likely cause | Action |
|---|---|---|
| `dim_date` / `dim_channel` / `dim_product` | source read error, transient cluster issue | check the stack; if transient, **Repair run** (reruns only failed + downstream tasks); if a real source change, fix the notebook |
| `fact_orders_line` | TW federated catalog unavailable, Shopify join change, schema drift | check the stack; verify TW source reachable; if schema changed, update notebook 04 |
| `dq_gate` (hard fail) | a real integrity violation **or** a schema/config drift (a YAML column name no longer matches the table) | read which check + table failed in the exception. Integrity → fix the data and rerun. Drift → align the YAML in `dq_configs/` to the real schema, update the repo copy, rerun |
| `dq_gate` (only WARNs, but failed) | a `range`/`freshness` check was marked `severity: fail` | review whether the threshold or the data is wrong |
| `success_digest` | run-history table write issue | low impact (data already built + gated); check `pipeline_run_history` permissions |

**Repair vs Run now**: use **Repair run** to rerun only the failed + skipped tasks
from a failed run (cheaper, preserves the run). Use **Run now** for a fresh full run.

---

## 6. Reruns & backfill

- **Same-day rerun**: `success_digest` is idempotent for the current day
  (delete-then-insert today's row), so reruns won't duplicate history.
- **Fact rebuild**: notebook 04 currently does a **full overwrite** (2025-07-01 →
  present) on every run, so a rerun fully refreshes the fact. (This becomes an
  incremental MERGE in Phase 4 Step 5; this section will be updated then.)
- **Config change**: after editing any `dq_configs/*.yaml`, update **both** the
  workspace copy (`slice_1/dq_configs/`, read by the gate) **and** the repo copy
  (`metrics-service/data_quality/configs/`), then rerun.

---

## 7. Ownership & related jobs

- **Owner**: Sia (data/analytics).
- **Related job**: `amazon_shipment_ingestion_weekly` (Amazon receiving-by-SKU,
  Medallion bronze→silver→gold, separate domain). Same email-on-failure standard.
- **Manual upstream task**: ERS product master CSV uploaded monthly (1st of month)
  to the Unity Catalog Volume; dim_product picks it up on the next run.

---

## 8. Change log

| Date | Change |
|---|---|
| 2026-05 | Initial 7-task DAG, DQ-as-gate (Spark-native), config-as-code |
| 2026-06 | Added dim_product Unknown member (key 0); fact coalesces unmatched product_key → 0 (Kimball FK integrity). Schedule unpaused (went live) on governed single-user Personal Compute — cluster-creation entitlement unavailable, serverless ruled out by `.cache()` |
