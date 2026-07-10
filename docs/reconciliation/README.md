# Reconciliation Methodology — Slice 1

> **Purpose**: Quantitative trust gate for the new analytics platform's Slice 1
> against the legacy Panoply system. Day 5 of the slice build, before stakeholder demo.

---

## Why this exists

Slice 1 migrates the `Style-channel (quantity)` PBI page from a legacy Panoply-backed
data path to the new Databricks Lakehouse platform. Both systems compute the same
business question — "how many units sold per style × channel × week" — but through
entirely different pipelines:

| Aspect | Legacy Panoply | New Platform |
|---|---|---|
| Source data | Shopify (Panoply auto-sync) + GA4 + ERS | Shopify (Fivetran) + Triple Whale + ERS |
| Channel attribution | GA4 `channelgrouping` | TW `channel_source` with `legacy_channel_group` mapping |
| Timezone | Static UTC-5 (DST-ignorant) | DST-aware `from_utc_timestamp('America/New_York')` |
| Date semantics | Mixed (PBI-derived US-week + Panoply native week) | ISO 8601 only (Decision 11) |
| Engine | Redshift (Panoply) | Spark SQL (Databricks) |

Differences are expected. The goal is to **quantify** them, distinguish "expected
< 2% diff" from "concerning drift", and surface results in a stakeholder-readable format.

---

## What this directory contains

```
docs/reconciliation/
├── README.md                           # this file
├── 01_new_platform_query.sql           # query against Databricks fact_orders_line
├── 02_panoply_legacy_query.sql         # query against Panoply Style_selling_dfNEW
├── run_reconciliation.py               # Python diff + report generator
├── data/                               # (gitignored) CSV inputs
│   ├── new_platform.csv                # output of query 1
│   └── panoply_legacy.csv              # output of query 2
└── reports/                            # (gitignored) generated reports
    ├── reconciliation_report.xlsx      # stakeholder-facing color-coded Excel
    ├── reconciliation_diff.csv         # machine-readable full diff
    └── reconciliation_summary.json     # overall stats
```

---

## Reconciliation grain

`(iso_year × iso_week × vend_id × legacy_channel_group)`

**Why this grain**:

- **Week-level** — daily reconciliation has too much noise from order-arrival timing;
  weekly aggregates smooth that out while still being granular enough to spot drift.
- **vend_id** (style) — the central business dimension; differences at the style level
  are actionable for merchandisers.
- **legacy_channel_group**, not `channel_source` — the new platform's `dim_channel`
  exposes both a TW-native name (`channel_source` like `google-ads`) and a GA4-style
  grouping (`legacy_channel_group` like `Paid Search`, Decision 15). For reconciliation
  we use `legacy_channel_group` because that's what Panoply has, enabling 1:1
  comparison.

---

## Default time window

**Last 7 complete days** (yesterday going back 7 days, today excluded).

**Why 7 days**:

- Covers a full week → every channel that has any traffic appears
- Excludes today because Fivetran daily sync may not have completed
- Small enough that the resulting Excel is scannable (typically 200-1000 rows)
- Recent enough that channel mapping ambiguities are minimized (TW data is most
  complete and well-mapped in recent windows)

To run a different window, edit the `WHERE` clauses in both SQL files.

---

## Thresholds & status categories

| Category | Definition | Color | Action |
|---|---|---|---|
| **PASS** | `\|diff%\|` < 2% | 🟢 green | None — within expected variance |
| **WARN** | 2% ≤ `\|diff%\|` < 5% | 🟡 yellow | Note in demo; spot-check causes |
| **FAIL** | `\|diff%\|` ≥ 5% | 🔴 red | Investigate; explain or fix before stakeholder sees |
| **MISSING_NEW** | new=0, panoply > 10 units | 🟠 orange | Likely TW didn't tag this bucket — investigate channel mapping |
| **MISSING_PANOPLY** | new > 10 units, panoply=0 | 🟠 orange | Likely new platform is picking up data legacy missed — verify and document |

### Why these thresholds (independent of ETL DQ thresholds)

The thresholds here are **wider than the ETL DQ thresholds in `notebook 04`** because
reconciliation has more legitimate sources of variance:

| Variance source | Direction | Expected magnitude |
|---|---|---|
| GA4 → TW channel mapping (e.g., GA4 "Paid Search" ≈ TW "google-ads" + "bing-ads" combined) | bidirectional | < 5% per bucket |
| DST-aware vs static -5h timezone | DST transition days only | < 1% on non-transition days, up to 5% on the 2 transition days per year |
| TW attribution recency (we use last_touch; legacy GA4 was last-click) | usually agrees | < 2% |
| Refund/replacement exclusion (legacy strips them; new keeps them with flags — Decision in inventory §5.1.7 Q B, may flip per stakeholder) | systematic skew | < 3% expected |

Summed in the worst case, ~10% variance can be entirely "expected." Anything above
that signals real drift worth investigating.

---
---

## Variance attribution (Slice 1, 2025-07-07..13 window)

Initial reconciliation showed a +3.17% systematic positive bias (new platform
higher). Root cause was traced — **not a data error** — to four order-class
exclusions baked into the legacy Panoply report that the new platform does not
yet replicate:

| Legacy exclusion | New-platform status |
|---|---|
| Exchange orders (`name LIKE '%EXC%'`) | Reproducible — applied in reconciliation query 1 |
| Refunded orders (`refund1_news`) | Partially reproducible via `is_refunded` flag |
| Replacement orders (`Replacements_news`) | Not yet — source table not ingested |
| Returnly-tagged returns (`tags LIKE '%returnly%'`) | Not yet — Shopify `tags` not in Fivetran feed |

After applying the two reproducible filters, residual variance narrows to ~2%,
attributable to the two not-yet-reproducible classes.

**Resolution path**: rather than scatter four `WHERE NOT IN` filters across every
query (the legacy approach), the business rule will be materialized once as an
`is_sales_attributable` flag on `fact_orders_line` — a single source of truth
consumed uniformly by reconciliation, the metrics API, and the future refunds
report. Tracked as a backlog item; requires ingesting replacement/refund source
tables and Shopify `tags` via Fivetran.

## How to run

### Prerequisites

```powershell
# From project root
pip install pandas openpyxl
```

### Step-by-step

**Step 1**: Run new-platform query.

1. Open Databricks SQL Editor in your workspace
2. Open `docs/reconciliation/01_new_platform_query.sql`
3. Copy-paste, run
4. Download result as CSV
5. Save to `docs/reconciliation/data/new_platform.csv`

**Step 2**: Run Panoply legacy query.

1. Open Panoply Web UI → SQL Editor
2. Open `docs/reconciliation/02_panoply_legacy_query.sql`
3. Copy-paste, run
4. Export result as CSV
5. Save to `docs/reconciliation/data/panoply_legacy.csv`

**Step 3**: Run the Python diff script.

```powershell
cd C:\Users\sia.song\analytics-platform
python docs/reconciliation/run_reconciliation.py
```

You'll see a console summary, and three files appear in `docs/reconciliation/reports/`:

- `reconciliation_report.xlsx` — stakeholder-facing, color-coded
- `reconciliation_diff.csv` — machine-readable, all rows
- `reconciliation_summary.json` — overall stats for dashboards / scripts

### Interpreting the report

The Excel has three sheets:

1. **Summary** — top-level stats; this is what stakeholder sees first
2. **All_Rows** — every reconciliation bucket, color-coded
3. **Needs_Attention** — only FAIL / MISSING rows, sorted by severity

**Success criterion for Slice 1 demo:**

> Overall quantity variance between the two platforms is within the 2% trust gate,
> AND any residual variance is fully attributed (not unexplained).

Per-bucket PASS/WARN/FAIL counts are reported for transparency, but the headline
metric is **overall % diff**. Bucket-level percentages are sensitive to
small-denominator amplification (a low-volume style can show a high pct_diff from
a 1-2 unit difference), so the aggregate figure is the honest trust signal.

If summary shows `PASS%` ≥ 95%, demo is green-lit. Below that, walk through
the `Needs_Attention` sheet and prepare explanations for each red row.
---

## Maintenance

This is not a one-time exercise. The reconciliation script is designed to be
re-run periodically during the migration period to detect drift:

- **Day 5**: First run, slice 1 launch
- **Week 2 post-launch**: Re-run to ensure stability
- **Monthly during migration**: Periodic sanity check
- **On any Decision change** (e.g., refund flag flip): Re-run to capture impact

When slice 2 (revenue) ships, this same methodology applies — just swap `SUM(quantity)`
for `SUM(line_price - total_discount)` in both SQL files.

---

## Engineering principles applied

- **Test in production through the front door**: rather than unit-testing the new
  ETL in isolation, validate end-to-end against the system it replaces.
- **Quantify, don't claim**: "correct migration" is meaningless without numbers;
  this report turns it into a measurable, reviewable artifact.
- **Single source of truth for thresholds**: the thresholds live in `run_reconciliation.py`
  and are reflected in the report, so stakeholder and engineer see the same definitions.
- **Designed for re-run**: the script reads CSVs (not live connections), so the same
  data can be re-analyzed with different thresholds without re-querying source systems.

---
