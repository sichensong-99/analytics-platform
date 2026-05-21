# Data Quality Framework

A lightweight, YAML-driven data quality validation framework for the Analytics Platform.
Built as a foundational module to enforce data contracts across multi-source pipelines
(Shopify via Fivetran, Triple Whale via custom pipeline).

---

## Why this exists

The platform ingests data from heterogeneous sources into Databricks Lakehouse.
Without quality gates, downstream models risk producing incorrect dashboards.

Goals:
- **Configuration-driven**: Business owners add new checks by editing YAML, not Python.
- **Extensible**: New check types only require adding one class — no changes to the runner.
- **Pipeline-ready**: Integrates as a quality gate in Databricks Workflows.

---

## Architecture

```
YAML config ──┐
              ├──> DQRunner ──> Checker instances ──> CheckResult list ──> Reporter
DataFrames ──┘
```

| Component | Responsibility |
|---|---|
| `checkers/base.py`     | Abstract `BaseChecker` + standardized `CheckResult` |
| `checkers/*.py`        | Concrete checkers (one per check type) |
| `runner.py`            | Reads YAML, instantiates checkers, executes checks |
| `reporter.py`          | Generates console/JSON reports from results |
| `configs/*.yaml`       | Per-table check definitions |

---

## Supported check types

| Type | Description | Example use case |
|---|---|---|
| `not_null`   | Column has no null values                          | `order_id` is never null |
| `unique`     | Column (or column combination) has no duplicates   | `order_id` is unique; or `(order_id, line_number)` is unique |
| `range`      | Numeric column values fall within `[min, max]`     | `total_price` between 0 and 100,000 |
| `freshness`  | Latest timestamp is within `max_age_hours`         | Data synced within last 48 hours |

---

## Quick start

### 1. Define checks in YAML

`configs/shopify_orders.yaml`:

```yaml
description: "Data quality checks for Shopify orders"
owner: "data-platform-team"
version: "1.0"

checks:
  - type: not_null
    table: shopify_orders
    column: order_id

  - type: unique
    table: shopify_orders
    column: order_id

  - type: range
    table: shopify_orders
    column: total_price
    min: 0
    max: 100000

  - type: freshness
    table: shopify_orders
    column: _fivetran_synced
    max_age_hours: 48
```

### 2. Run from Python

```python
from data_quality.runner import DQRunner
from data_quality.reporter import Reporter

runner = DQRunner.from_yaml("data_quality/configs/shopify_orders.yaml")
results = runner.run({"shopify_orders": orders_df})

print(Reporter.to_console(results))
# or for pipeline integration:
json_report = Reporter.to_json(results)
```

### 3. Sample output

```
======================================================================
DATA QUALITY REPORT
======================================================================
Total Checks:  6
Passed:        3
Failed:        3
Pass Rate:     50.0%
----------------------------------------------------------------------

📋 Table: shopify_orders
  ❌ FAIL [notnull].order_id  →  1 null values found
  ✅ PASS [notnull].created_at
  ✅ PASS [notnull].total_price
  ❌ FAIL [unique].order_id  →  2 duplicate rows found
  ❌ FAIL [range].total_price  →  1 values out of range [0, 100000]
  ✅ PASS [freshness]._fivetran_synced
======================================================================
```

---

## Extending the framework

Adding a new check type takes ~30 lines of code:

1. Create `checkers/my_check.py`, inherit from `BaseChecker`, implement `check()`
2. Register in `runner.py`:
```python
   CHECKER_REGISTRY = {
       ...,
       "my_check": MyChecker,
   }
```
3. Use it in YAML:
```yaml
   - type: my_check
     table: my_table
     column: my_column
```

---

## Testing

```bash
cd metrics-service
python data_quality/tests/test_not_null.py        # 3 unit tests
python data_quality/tests/test_all_checkers.py    # 8 unit tests
python data_quality/tests/test_runner.py          # 4 end-to-end tests
```

---

## Roadmap

- [x] Pandas DataFrame support (mock / small data)
- [ ] PySpark DataFrame support (Databricks integration)
- [ ] Integration with Databricks Workflows (quality gate task)
- [ ] Slack / email alerting on failure
- [ ] DQ results historical store (track quality trends over time)

---

## Design decisions

| Decision | Rationale |
|---|---|
| Abstract base class for checkers | New check types only require subclassing; runner stays unchanged |
| YAML-driven config | Business owners can add checks without Python knowledge |
| `CheckResult` dataclass | Single standardized output shape; trivial to serialize / aggregate |
| Pandas first, Spark later | Faster local iteration during development; minimal API surface change to swap engines |
| Errors return `CheckResult` instead of raising | A misconfigured check shouldn't crash the whole DQ run |