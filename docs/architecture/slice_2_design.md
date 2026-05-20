# Slice 2 Architecture Design Doc — `Style-channel (revenue)` Page

> **Second vertical slice**, building on Slice 1's foundation. Revenue measure replaces quantity; all underlying dim/fact infrastructure reused unchanged.

---

## Document Control

| Field | Value |
|---|---|
| Author | Sia Song |
| Created | 2026-05-19 |
| Version | 1.0 |
| Status | 🟡 Pre-implementation (starts after Slice 1 demo) |
| Reviewers | Self; share with Leader at Slice 1 demo to set expectations |
| Supersedes | None |
| Related Docs | `docs/architecture/slice_1_design.md` (canonical reference — read first), `PROJECT_CONTEXT.md` Decision Log, `docs/existing_data_inventory.md` §5.1 |

### Changelog

| Version | Date | Author | Change |
|---|---|---|---|
| 1.0 | 2026-05-19 | Sia | Initial Slice 2 design — revenue measure on top of Slice 1's star schema. |

---

## 1. Executive Summary

### 1.1 What Slice 2 delivers

Slice 2 delivers the `Style-channel (revenue)` PBI page on the new analytics
platform. This page answers the same business question as Slice 1's
`Style-channel (quantity)`, except the measure changes from "how many units"
to "how much net revenue". Everything else — same data sources, same star
schema, same channel taxonomy, same time semantics, same UI layout — is
shared with Slice 1.

The strategic point of Slice 2 is **demonstrating zero-marginal-cost slice
expansion**: a working slice 1 → adding slice 2 is mostly configuration, not
new infrastructure. This validates the platform's metric-layer-driven design.

### 1.2 Why Slice 2 is the right second slice

Three reasons:

1. **Highest infrastructure reuse**: shares 100% of Slice 1's dim/fact tables.
   The slice 2 effort is concentrated in the metric layer and frontend.
2. **Same business audience**: marketing analysts use both pages weekly. A
   working Slice 2 immediately doubles platform value for the primary user
   cohort.
3. **Validates the metric layer**: if Slice 2 truly requires only YAML +
   minimal UI work, it proves the Phase 2A metric service was well-designed.
   If it requires unexpected fact changes, that's a design feedback signal
   worth catching now (before slice 3 introduces real new requirements).

### 1.3 Success criteria

Slice 2 is "done" when:

1. **Functional**: All four visuals on the new portal page render correctly
   with real Databricks data (no mock).
2. **Correct**: 7-day reconciliation against Panoply legacy at (iso_week ×
   style × channel) grain shows < 2% absolute revenue difference for ≥ 95%
   of buckets.
3. **Performant**: P95 page load (cold cache) < 4s; warm cache target deferred
   to Phase 5.
4. **Quality-gated**: All slice 1 DQ checks still pass (slice 2 adds no new
   ones — the same fact_orders_line table is the source).
5. **Documented**: This design doc + a Slice 2 entry in `PROGRESS.md`.

### 1.4 Timeline — 2.5 days total

Slice 2's compressed timeline is intentional and the central claim of this
design doc. Compare to Slice 1's 5 days:

| Day | Slice 1 (for reference) | Slice 2 |
|---|---|---|
| Day 1 | Star schema design | **N/A — reused from Slice 1** |
| Day 2 | dim ETL | **N/A — same dim tables** |
| Day 3 | fact ETL | **N/A — same fact_orders_line** |
| Day 4 | FastAPI metric + YAML | YAML metric + light FastAPI wiring (~half day) |
| Day 5 | Next.js page + reconciliation + demo | Next.js page (mostly copy of Slice 1 page with measure swap) + reconciliation + demo (~1 day) |
| Buffer | — | Reconciliation refinement + edge cases (~half day) |

The contrast itself is a resume signal: "each subsequent slice cost 50% less
than the previous, validating the platform-layer investment of the first slice."

---

## 2. Background & Context

### 2.1 What changes vs Slice 1

| Aspect | Slice 1 | Slice 2 | Delta |
|---|---|---|---|
| PBI page name | `Style-channel (quantity)` | `Style-channel (revenue)` | name only |
| Measure | `SUM(quantity)` | `SUM(line_price - total_discount)` | new measure expression |
| Unit | units | USD ($) | new unit |
| Source fact | `fact_orders_line` | `fact_orders_line` | unchanged |
| Source columns from fact | `quantity` | `line_price`, `total_discount` | columns already in slice 1 fact (forward-loaded) |
| Dim tables | dim_date, dim_channel, dim_product | same | unchanged |
| Time semantics | ISO 8601 weeks | ISO 8601 weeks | unchanged |
| Channel taxonomy | dual-display (channel_source + legacy_channel_group) | same | unchanged |
| Visual layout | 4 visuals (time slicer / 3 filter slicers / line chart / drill matrix) | same 4 visuals | unchanged |
| Y-axis values | unit count | dollar amount | format change (`$X,XXX.XX`) |
| YAML metric file | `quantity_by_style_channel_week.yaml` | `revenue_by_style_channel_week.yaml` | new file |
| Frontend page | `/dashboards/style-channel-quantity` | `/dashboards/style-channel-revenue` | new file (mostly copy) |
| Reconciliation | quantity diff vs Panoply | revenue diff vs Panoply | same methodology, different measure |

### 2.2 Why `line_price - total_discount` (not gross `line_price`)

Legacy `Style_selling_dfNEW.dollars` is net revenue (after line-item discount,
before refund). This is the de-facto definition the team has used in PBI for
years and what Leader expects to see on the new page.

The expression decomposes as:

- `line_price`: per-unit price × quantity already aggregated into the SKU-line
  (Shopify's `order_line.price` is the line subtotal, not unit price).
- `total_discount`: line-item discount allocation already pre-computed by
  Shopify (covers automatic discounts, manual discounts, and discount code
  apportionment).
- Net = price − discount = what the customer actually paid for that line item
  (excluding tax and shipping, which are per-order, not per-line).

This matches what Panoply legacy stores in `Style_selling_dfNEW.dollars` per
`docs/legacy_panoply_etl.md` §2 and confirmed empirically by spot-checking 20
random orders during Slice 1 design.

### 2.3 What about refunds?

Slice 2's `SUM(line_price - total_discount)` is **gross-of-refund** — refunded
units are still included. This matches:

- Legacy `Style_selling_dfNEW.dollars` behavior (refunds excluded at the
  `shopify_orders_order2` upstream filter, see `legacy_panoply_etl.md` §2.3).
- Open Question Q-B from inventory §5.1.7 still pending Leader alignment.

If Leader prefers net-of-refund after slice 2 demo, the change is two lines
in the YAML metric SQL (`LEFT JOIN order_line_refund` + subtract refunded
amount). This is **slice 3 scope**, not slice 2.

---

## 3. Goals & Non-goals

### 3.1 In scope (Slice 2)

- One new YAML metric: `revenue_by_style_channel_week`.
- One new FastAPI endpoint: `GET /metrics/revenue_by_style_channel_week`.
- One new Next.js page: `/dashboards/style-channel-revenue`.
- Reconciliation methodology re-applied with measure swapped.
- Reuse of all Slice 1 dim/fact tables, DQ framework, and Workflows orchestration.

### 3.2 Out of scope (Slice 3+)

- Net-of-refund revenue (slice 3 — depends on Leader Q-B decision).
- Average order value (AOV) — closer to a Slice 3-style metric requiring
  order-grain aggregation logic.
- Cost-of-goods-sold (COGS) — requires ERS `cost` column join, deferred.
- Multi-currency normalization — currently single-currency (USD), deferred
  until international expansion.

---

## 4. Architecture Overview

```
   ┌────────────────────────────────────────────────────────────────┐
   │                    Already in Place from Slice 1               │
   │                                                                │
   │     Shopify (Fivetran)         Triple Whale (custom)           │
   │              │                          │                      │
   │              └──── PySpark ETL ─────────┘                      │
   │                          │                                     │
   │                fact_orders_line                                │
   │        (already contains line_price + total_discount)          │
   │                          │                                     │
   │                 dim_date, dim_channel, dim_product             │
   │                          │                                     │
   │                          │                                     │
   ╞══════════════════════════╪═══════════════════════════════════ ═╡
   │                          ▼                                     │
   │                 ⭐ Slice 2 additions:                          │
   │                                                                │
   │   metrics-service/metrics/                                     │
   │     ├── quantity_by_style_channel_week.yaml  (slice 1)         │
   │     └── revenue_by_style_channel_week.yaml   ⭐ NEW            │
   │                                                                │
   │   FastAPI: new endpoint auto-discovered from YAML              │
   │     (no new endpoint code — YAML-driven design pays off)       │
   │                                                                │
   │   Next.js: new page                                            │
   │     └── /dashboards/style-channel-revenue/page.tsx ⭐ NEW      │
   │                                                                │
   └────────────────────────────────────────────────────────────────┘
```

The grey area is reused. The starred area is Slice 2's net-new work.

---

## 5. Data Sources

All sources identical to Slice 1. See `slice_1_design.md` §5 for full details.

**Important**: `fact_orders_line` already carries `line_price` and
`total_discount` (forward-loaded in Slice 1 specifically anticipating Slice 2,
per Decision 16-style forward-design discipline). No fact ETL change required.

---

## 6. Target Star Schema

**Unchanged from Slice 1.** The star schema in `slice_1_design.md` §6 is the
canonical reference. Slice 2 adds zero tables and zero columns.

### Forward-design payoff

Slice 1's fact_orders_line DDL deliberately included `line_price` and
`total_discount` even though only `quantity` was needed for Slice 1.

Resume framing: "Forward-loaded `line_price` and `total_discount` into the
slice 1 fact table to anticipate slice 2's revenue measure, eliminating the
need for fact schema evolution between slices."

---

## 7. ETL Module Breakdown

**Unchanged from Slice 1.** Same four notebooks orchestrated by the same
Workflows DAG.

---

## 8. Metric Definition

The full Slice 2 deliverable is concentrated in this section.

### 8.1 YAML metric file

File: `metrics-service/metrics/revenue_by_style_channel_week.yaml`

```yaml
name: revenue_by_style_channel_week
version: 1.0.0
description: |
  Net revenue (price - discount, gross-of-refund) per ISO week × style ×
  channel, with optional drill-down to item_description (SKU level).
  Sourced from new Lakehouse fact_orders_line. Migrated from legacy Panoply
  Style_selling_dfNEW.dollars.
owner: sia.song
unit: USD
grain: [iso_year, iso_week, vend_id, channel_source]
optional_drilldown: [item_description]
parameters:
  date_from: { type: date, required: true }
  date_to:   { type: date, required: true }
  channels:  { type: list[string], required: false }
  seasons:   { type: list[string], required: false }
  vend_ids:  { type: list[string], required: false }
sql: |
  SELECT
      d.iso_year, d.iso_week,
      p.vend_id, p.item_description,
      c.channel_source AS channel_name,
      c.legacy_channel_group,
      SUM(f.line_price - f.total_discount) AS revenue_usd
  FROM analytics_platform_32degrees.fact_orders_line f
  JOIN analytics_platform_32degrees.dim_date    d ON f.date_key    = d.date_key
  JOIN analytics_platform_32degrees.dim_product p ON f.product_key = p.product_key
  JOIN analytics_platform_32degrees.dim_channel c ON f.channel_key = c.channel_key
  WHERE d.full_date BETWEEN :date_from AND :date_to
    AND (:channels IS NULL OR c.channel_source IN (:channels))
    AND (:seasons  IS NULL OR p.season         IN (:seasons))
    AND (:vend_ids IS NULL OR p.vend_id        IN (:vend_ids))
  GROUP BY ALL
changelog:
  - version: 1.0.0
    date: 2026-XX-XX  # populated at slice 2 implementation
    author: sia.song
    change: Initial slice 2 implementation. Migrated from Panoply
            Style_selling_dfNEW.dollars (net-of-discount, gross-of-refund).
related_metrics:
  - quantity_by_style_channel_week  # same grain, same source, complementary measure
```

### 8.2 What's identical to Slice 1's metric

Comparison highlights the YAML-driven design's leverage:

| YAML field | quantity slice 1 | revenue slice 2 |
|---|---|---|
| name | `quantity_by_style_channel_week` | `revenue_by_style_channel_week` |
| version | 1.0.0 | 1.0.0 |
| owner | sia.song | sia.song |
| grain | `[iso_year, iso_week, vend_id, channel_source]` | **same** |
| optional_drilldown | `[item_description]` | **same** |
| parameters | (date_from, date_to, channels, seasons, vend_ids) | **same** |
| SQL structure | `SELECT ... JOIN dims ... WHERE ... GROUP BY ALL` | **same template** |
| SQL measure | `SUM(f.quantity) AS quantity` | `SUM(f.line_price - f.total_discount) AS revenue_usd` |
| unit | `units` | `USD` |

**12 of 13 fields identical**. The metric layer's value is exactly this:
new metric, new SQL measure, **zero engineering elsewhere**.

---

## 9. API Endpoint Contract

### 9.1 Endpoint

```
GET /metrics/revenue_by_style_channel_week
```

Identical parameter signature and response shape as
`/metrics/quantity_by_style_channel_week`, with one field rename:

```json
{
  "metric": "revenue_by_style_channel_week",
  "version": "1.0.0",
  "data": [
    {
      "iso_year": 2026,
      "iso_week": 19,
      "vend_id": "PACKBAG",
      "item_description": "Packable Tote Bag",
      "channel_name": "google-ads",
      "legacy_channel_group": "Paid Search",
      "revenue_usd": 28473.50
    },
    ...
  ],
  "_meta": { "row_count": 8421, "elapsed_ms": 1273 }
}
```

### 9.2 Endpoint auto-discovery

Per Slice 1 design (Decision 2 — YAML-driven metric DSL), the FastAPI service
auto-discovers metric YAML files at startup. Adding `revenue_by_style_channel_week.yaml`
and restarting the service is sufficient — **no new Python code is needed**.

This is the design payoff. If we had hard-coded endpoints in Slice 1, Slice 2
would require adding a new endpoint handler, parameter validation, SQL
templating, etc. The YAML-driven approach eliminates all of that.

---

## 10. Frontend Wire-up

### 10.1 New page

File: `frontend/<location>/style-channel-revenue/page.tsx` (path depends on
Slice 1's chosen router structure; will mirror exactly).

### 10.2 What differs from Slice 1 page

| Element | Slice 1 page | Slice 2 page |
|---|---|---|
| URL path | `/dashboards/style-channel-quantity` | `/dashboards/style-channel-revenue` |
| Page title | "Style × Channel — Quantity" | "Style × Channel — Revenue" |
| Metric API call | `/metrics/quantity_by_style_channel_week` | `/metrics/revenue_by_style_channel_week` |
| Y-axis value field | `quantity` | `revenue_usd` |
| Y-axis label | "Units sold" | "Revenue (USD)" |
| Value formatter | `{value:,} units` | `${value:,.2f}` |
| ECharts color palette | (whatever Slice 1 uses) | **swap to a slightly different palette** to visually distinguish |
| Matrix cell format | integer | currency |

### 10.3 Implementation approach: copy + targeted edits

Slice 2 page is built by **literally copying** the Slice 1 page file and
making the focused changes above. This is intentional — the page-level
duplication is small enough that abstraction (a shared component parameterized
by metric name) would be premature.

Slice 3 onward may justify abstraction if pages keep diverging in only the
measure dimension. For now, copy + diff is the cleanest path.

### 10.4 Cross-page navigation

The portal navigation gets a new entry. Both pages live under the same
"Sales Attribution" section in the sidebar, so users browsing one will see
the other.

Optional UX nicety (deferred to Slice 3+): a "View this in revenue" / "View
this in units" link at the top of each page that preserves current filters.

---

## 11. Reconciliation Methodology

### 11.1 Reuse Slice 1's framework

`docs/reconciliation/` already houses the SQL/Python/Excel tooling. Slice 2
adds a parallel set with the measure swapped.

### 11.2 New files

```
docs/reconciliation/
├── 01_new_platform_query.sql            (slice 1 — quantity)
├── 02_panoply_legacy_query.sql          (slice 1 — quantity)
├── 03_new_platform_query_revenue.sql    ⭐ NEW — slice 2 revenue
├── 04_panoply_legacy_query_revenue.sql  ⭐ NEW — slice 2 revenue
├── run_reconciliation.py                (slice 1)
├── run_reconciliation_revenue.py        ⭐ NEW (or refactor to parametrize)
└── README.md                            (updated to cover both slices)
```

### 11.3 The two new SQL queries

**`03_new_platform_query_revenue.sql`** mirrors `01_new_platform_query.sql`
exactly except for the SELECT line:

```sql
SUM(f.line_price - f.total_discount) AS revenue_new
-- (replaces SUM(f.quantity) AS qty_new)
```

**`04_panoply_legacy_query_revenue.sql`** mirrors `02_panoply_legacy_query.sql`:

```sql
SUM(dollars) AS revenue_panoply
-- (replaces SUM(quantity) AS qty_panoply)
```

### 11.4 Threshold considerations

The < 2% PASS threshold from Slice 1 carries over, but **revenue diff is
typically slightly higher than quantity diff** because:

- Discount allocation can vary slightly between systems (legacy used pre-Fivetran
  Panoply normalization; new uses Fivetran-as-is).
- Currency rounding in aggregation.

Empirically expect 1-3% diff on average; bump WARN to 3% and FAIL to 6% if
slice 2 reconciliation surfaces this consistently.

### 11.5 Optional refactor: parametrize the Python script

The `run_reconciliation.py` script can be made measure-agnostic by adding a
`--measure` CLI flag:

```bash
python docs/reconciliation/run_reconciliation.py --measure quantity
python docs/reconciliation/run_reconciliation.py --measure revenue
```

This is a nice-to-have, not blocking slice 2 demo. The duplication-then-refactor
path is more honest about uncertainty: until we see slice 3's measure, we don't
know if the parametrization should be `--measure` or something more general.

---

## 12. Risks & Mitigations

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R1 | Revenue diff vs Panoply > 2% due to discount allocation differences | Medium | Medium | Investigate first; if explainable, document as expected and widen threshold to 3%. Pre-explain in demo. |
| R2 | Leader asks for net-of-refund during demo | High | Low (slice 3 work) | Pre-prepare answer: "Slice 3 introduces refund flags; for now we mirror legacy's gross-of-refund definition." |
| R3 | `line_price` or `total_discount` has nulls we didn't catch in slice 1 | Low | Medium | Add to Slice 2 DQ config: `not_null` check on these columns post-slice-1 stability period |
| R4 | YAML auto-discovery doesn't pick up the new file (deployment issue) | Low | High | Add to slice 2 runbook: verify endpoint reachable before demo by hitting `/metrics` listing endpoint |

---

## 13. Open Questions

To confirm with Leader during/after slice 2 demo:

1. **Net-of-refund preference**: should slice 2 displays subtract refunds by
   default (with a "show gross" toggle), or vice versa? Currently gross-of-refund
   per legacy. (This is Q-B from `existing_data_inventory.md` §5.1.7.)

2. **Multi-currency**: any near-term plan for international expansion that
   would require currency conversion? Affects slice 4+ design.

3. **Slice 3 priority**: refunds vs ROAS — which is the next slice? Refunds is
   technically easier (one new dim + one new fact), ROAS is more impressive
   (multi-model attribution). Recommendation: refunds (easier wins build
   demo momentum; ROAS as slice 4).

---

## 14. Estimated Implementation Plan — 2.5 days

| Half-day | Tasks |
|---|---|
| Day A AM | Write `revenue_by_style_channel_week.yaml`. Restart FastAPI; verify endpoint discovered; smoke-test with curl. |
| Day A PM | Copy Slice 1 page to revenue page; swap metric name, field name, formatter, Y-axis label, palette. |
| Day B AM | Write reconciliation SQL pair for revenue; run on Slice 1's existing fact data; validate diff < 3%. |
| Day B PM | Polish demo (filters, drill-down, CSV export work end-to-end on revenue). Update PROGRESS.md. |
| Day C AM | Buffer / edge cases / surprise findings during demo prep. |

If everything goes smoothly, Day C AM is unused — that's fine, slack absorbs
risk. The plan accommodates Slice 2 finishing in 2 days flat or stretching to
3 days; either outcome is acceptable.

---

## 15. What this slice proves (strategic narrative)

The point of Slice 2 isn't the revenue page — Leader cares but doesn't lose
sleep over not having it. The strategic point is **demonstrating compound
returns on platform investment**:

| Investment | When | Slice 2 payoff |
|---|---|---|
| YAML-driven metric layer | Phase 2A | New endpoint with zero code |
| Forward-loaded fact columns | Slice 1 Day 1 | No fact schema change |
| Conformed dim tables | Slice 1 Day 2 | No dim work |
| Workflows DAG | Phase 4 | No orchestration change |
| Reconciliation framework | Slice 1 H2 | Parametric reuse |

This is the resume narrative arc: not "I built 4 slices" but **"I built a
platform that let slice 1 take 5 days, slice 2 take 2.5 days, slice 3 take ~5
days again (genuine complexity), and slice 4 take 2.5 days. Total: 15 days
for 4 production analytics pages, with cumulative engineering leverage."**

---

## 16. Appendix

### A. Resume notes

This design contributes the following resume points:

1. **"Designed and executed second vertical slice in 50% the time of slice 1
   by leveraging YAML-driven metric layer, conformed dimensions, and forward-
   loaded fact columns — empirically validating the platform-layer investment."**

2. **"Forward-loaded `line_price` and `total_discount` into slice 1's
   `fact_orders_line` deliberately to anticipate slice 2's revenue measure
   — eliminating any fact-table schema evolution between slices."**

3. **"Reused reconciliation methodology with measure swap, demonstrating the
   framework's parametric extensibility from quantity to revenue without
   rewriting tooling."**

4. **"Authored design doc before implementation for slice 2 (300+ lines)
   following the same discipline as slice 1, codifying engineering practice
   that 'every slice has a design doc' regardless of size."**

### B. References

- `docs/architecture/slice_1_design.md` — canonical reference for shared design
- `docs/architecture/phase4_orchestration_design.md` — orchestration unchanged
- `docs/existing_data_inventory.md` §5.1 — original quantity page reverse engineering (revenue page reverse engineering still pending in §5.2 via H3)
- `docs/legacy_panoply_etl.md` §2 — legacy `dollars` measure definition
- `docs/reconciliation/README.md` — methodology base

### C. Slice numbering convention

This is "Slice 2" per the project's vertical-slice methodology (Decision 10).
Numbering reflects build order, not business importance. Slice 1 was chosen
first as the highest-infrastructure-reuse foundation; Slice 2 is chosen second
as the highest-leverage demonstration of that foundation. Future slices
(3 = refunds, 4 = ROAS, etc.) will be ordered by a combination of business
demand, technical complexity, and resume-narrative impact.

---

*End of Slice 2 Architecture Design Doc v1.0.*
