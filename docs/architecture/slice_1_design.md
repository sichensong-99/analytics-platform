# Slice 1 Architecture Design Doc — `Style-channel (quantity)` Page

> **End-to-end vertical slice**: Shopify + Triple Whale + ERS → Lakehouse star schema → FastAPI metric service → Next.js portal

---

## Document Control

| Field | Value |
|---|---|
| Author | Sia Song |
| Created | 2026-05-19 |
| Version | 1.0 |
| Status | 🟢 Approved for Implementation |
| Reviewers | Self (project owner). Will share with Leader after Day 5 demo. |
| Supersedes | None (first slice design doc) |
| Related Docs | `docs/data_modeling/star_schema_ddl.sql` (v1.1), `docs/existing_data_inventory.md` §5.1, `docs/legacy_panoply_etl.md` (v3), `NORTH_STAR.md`, `PROJECT_CONTEXT.md` Decision Log §10–16 |

### Changelog

| Version | Date | Author | Change |
|---|---|---|---|
| 1.0 | 2026-05-19 | Sia | Initial version covering Slice 1 end-to-end design. |

---

## 1. Executive Summary

### 1.1 What this slice delivers

Slice 1 is the **first end-to-end vertical slice** of the new internal analytics platform replacing Power BI Service. It delivers the `Style-channel (quantity)` PBI page (PBI tab #2) on the new platform — from raw Shopify + Triple Whale (TW) data in Databricks, through a Kimball star schema, to a FastAPI metric service, to a Next.js portal page rendering the four PBI visuals (time slicer, three filter slicers, line chart, drill-down matrix).

### 1.2 Why vertical slice over waterfall (Decision 10)

A waterfall approach would build all fact/dim tables first, then the service layer, then the frontend — meaning Leader sees nothing until everything is done. Vertical slice cuts the platform thin and end-to-end: each slice surfaces real data, real integration risks, and real stakeholder feedback early. Slice 1 also paves the path for slices 2+ (revenue, refunds, ROAS), which will largely reuse Slice 1's fact/dim infrastructure.

### 1.3 Success criteria

A slice is "done" when **all five** are true:

1. **Functional**: All four visuals on the new portal page render correctly using real Databricks data (no mock).
2. **Correct**: 7-day reconciliation against Panoply legacy `Style_selling_df` shows < 2% absolute difference at the (week × style × channel) grain.
3. **Performant**: P95 page load (cold cache) < 4s; P95 (warm cache) < 800ms.
4. **Quality-gated**: All 4 DQ checks pass (PK uniqueness on dims, FK referential integrity on fact, freshness on fact, expected row count range on fact).
5. **Documented**: This design doc + a Slice 1 summary in `PROGRESS.md` exist and are committed.

### 1.4 Timeline

| Day | Phase | Output |
|---|---|---|
| Pre-Day 2 (current) | Pre-permission preparation | This design doc, PySpark notebook skeletons, YAML metric def, mock-data UI |
| Day 2 (= permission day) | Dim ETL | `dim_date` loaded, `dim_channel` seeded, `dim_product` built |
| Day 3 | Fact ETL | `fact_orders_line` built via Shopify + TW + ERS join |
| Day 4 | Service layer | FastAPI connects to real Databricks SQL Warehouse; YAML metric SQL verified |
| Day 5 | Wire-up + DQ | Next.js page consumes real API; full DQ run; reconciliation against Panoply |
| Day 5 EOD | **Leader Demo** | Live walkthrough of the page on the new platform |

---

## 2. Background & Context

### 2.1 Why this page is Slice 1

`Style-channel (quantity)` was deliberately chosen as the first slice for three reasons:

1. **Highest reuse**: It exercises the *entire* sales attribution pipeline — Shopify line items × TW channel attribution × ERS product master — meaning the four tables built here become the foundation for slices 2 (revenue), 3 (refunds), and 4 (ROAS). Picking a simpler page (e.g., a single-source freight cost page) would build infrastructure that slice 2 couldn't reuse.
2. **Single-fact simplicity**: Per `existing_data_inventory.md` §5.1.3, the entire page sources from one legacy fact (`Style_selling_df`). No multi-fact merge complexity for the first slice.
3. **Leader visibility**: Marketing and merchandising use this page weekly. A working demo creates immediate stakeholder buy-in for the platform direction.

### 2.2 Legacy system summary

The Panoply legacy system implements this page via `Style_selling_df`, a row-level fact built by joining Shopify line items, GA4 attribution (with multi-key fallback joins on `transactionId`), and ERS product master (with sku → item_description graceful degradation). See `legacy_panoply_etl.md` §2 for the full reverse-engineered logic. Slice 1 reimplements this on the new platform with two material changes:

- **Channel source**: GA4 → Triple Whale (per project-level Decision 8). Channel taxonomy follows TW UI native labels with a `legacy_channel_group` field for cognitive continuity (Decision 15).
- **Time semantics**: ISO 8601 weeks only (Decision 11). Legacy used both US-week (Sunday-start) and ISO inconsistently across visuals — this is documented in `existing_data_inventory.md` §5.1.4 Insight #2.

### 2.3 Stakeholders

| Persona | Role | Slice 1 interaction |
|---|---|---|
| Leader | Project sponsor (cost reduction + platform direction) | Day 5 demo recipient; reconciliation diff < 2% is the trust threshold |
| Marketing analyst | Primary end user of this page | Validation user after Day 5; their feedback shapes slice 2 |
| TW pipeline owner | Source data owner | Already consulted on TW meta-categories (Decision 14); no further blocker for slice 1 |
| Databricks platform owner | Schema/Volume provisioning | Blocker until permissions issued (email sent 2026-05-18) |

---

## 3. Goals & Non-goals

### 3.1 In scope (Slice 1)

- Four physical tables: `dim_date`, `dim_channel`, `dim_product`, `fact_orders_line` (DDL v1.1 already authored).
- ETL window: 2025-07-01 onward (rationale: TW data begins on this date — Decision 13).
- One YAML metric: `quantity_by_style_channel_week`.
- One FastAPI endpoint exposing the metric with filter parameters.
- One Next.js page rendering the four PBI visuals.
- Four DQ checks instrumenting the four new tables.
- 7-day reconciliation report comparing new platform vs Panoply legacy.

### 3.2 Out of scope (Slice 2+)

- Revenue, refund, replacement, freight, ROAS metrics — slices 2, 3, 4, 5.
- SCD2 on `dim_product` — deferred per Decision 12 (YAGNI).
- GA4 funnel metrics (page view, add-to-cart, sessions) — outside attribution scope per Decision 9.
- Streaming / real-time channel anomaly monitoring — Phase 4.5.
- Cross-year data prior to 2025-07-01 — future ETL window expansion, schema already temporally unbounded (Decision 13).

---

## 4. Architecture Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                  Source Layer (already in Databricks)            │
│                                                                  │
│  Shopify (Fivetran)              Triple Whale (custom pipeline)  │
│  mvdevdatabricks.shopify_32degrees    mvdev_federated_catalog    │
│    ├── order            ~2.4M           .triple_whale            │
│    └── order_line       ~12M              ├── attribution_order  │
│                                           └── attribution_order_ │
│                                               click              │
│                                                                  │
│  ERS Product Master (manual monthly upload)                      │
│  mvdevdatabricks.analytics_platform_32degrees.raw_uploads        │
│    └── ers_product_master_YYYYMMDD.csv                           │
└──────────────────────────────────────────────────────────────────┘
                                ↓ PySpark ETL (Databricks notebooks)
┌──────────────────────────────────────────────────────────────────┐
│                Lakehouse Star Schema (Slice 1)                   │
│                mvdevdatabricks.analytics_platform_32degrees      │
│                                                                  │
│      dim_date            dim_channel          dim_product        │
│         │                     │                    │             │
│         └───────────┬─────────┴──────────┬─────────┘             │
│                     │                    │                       │
│                fact_orders_line (row-level, ~10M rows)           │
│                     · date_key, channel_key, product_key         │
│                     · quantity (slice 1 measure)                 │
│                     · line_price, total_discount (slice 2 ready) │
└──────────────────────────────────────────────────────────────────┘
                                ↓ SQL (Databricks SQL Warehouse)
┌──────────────────────────────────────────────────────────────────┐
│                Metric Layer (YAML DSL)                           │
│                metrics-service/metrics/                          │
│                  └── quantity_by_style_channel_week.yaml         │
│                       · version: 1.0.0                           │
│                       · SQL template with parameter binding      │
└──────────────────────────────────────────────────────────────────┘
                                ↓ HTTP/JSON
┌──────────────────────────────────────────────────────────────────┐
│                FastAPI Metric Service                            │
│                  GET /metrics/quantity_by_style_channel_week     │
│                  + JWT auth, param validation, CSV export        │
└──────────────────────────────────────────────────────────────────┘
                                ↓ fetch
┌──────────────────────────────────────────────────────────────────┐
│                Next.js Portal                                    │
│                  /dashboards/style-channel-quantity              │
│                    · Time slicer (Visual 1)                      │
│                    · 3 filter slicers (Visual 2)                 │
│                    · Channel line chart (Visual 3)               │
│                    · Drill-down matrix (Visual 4)                │
└──────────────────────────────────────────────────────────────────┘
```

---

## 5. Data Sources

### 5.1 Shopify (via Fivetran)

| Property | Value |
|---|---|
| Catalog.schema | `mvdevdatabricks.shopify_32degrees` |
| Tables used (slice 1) | `order`, `order_line` |
| Refresh | Fivetran daily incremental |
| Volume (slice 1 window) | order: ~2.4M rows total, ~2M in window. order_line: ~12M total, ~10M in window. |
| Owner | Fivetran connector owner (colleague) |
| Freshness SLA | Best-effort daily; not yet formalized |
| Validation status | ✅ Source reconciled vs Panoply (8-day cumulative diff 0.5%, see Issue #1 in inventory) |

### 5.2 Triple Whale (via custom pipeline)

| Property | Value |
|---|---|
| Catalog.schema | `mvdev_federated_catalog.triple_whale` (cosmetic catalog name — not actual Lakehouse Federation) |
| Tables used (slice 1) | `attribution_order`, `attribution_order_click` |
| Refresh | Custom pipeline (owned by TW colleague) |
| Volume (slice 1 window) | attribution_order: ~2M. attribution_order_click: ~10M (avg 5 touchpoints per order). |
| Attribution model used | `last_touch` (matches TW UI default and Leader's TW exposure) — see §8.3 for decision rationale |
| Freshness SLA | Best-effort daily |
| Validation status | ✅ Cross-source match rate ≥ 99.85% across 11 months (2025-07 to 2026-05) |

### 5.3 ERS Product Master (manual upload)

| Property | Value |
|---|---|
| Catalog.schema.volume | `mvdevdatabricks.analytics_platform_32degrees.raw_uploads` |
| Filename convention | `ers_product_master_YYYYMMDD.csv` |
| Refresh | Manual monthly upload by Sia |
| Volume | ~50K SKUs |
| Owner | Sia |
| Validation status | ⏳ Pending — needs Volume creation (blocked on Databricks permission) |
| Fallback strategy | If a SKU is not found in ERS, follow legacy graceful-degradation pattern: try `item_description` match before defaulting to `dim_product.product_key = -1` (unknown product placeholder, slot reserved in dim_product) |

---

## 6. Target Star Schema

### 6.1 ER diagram (logical)

```
        ┌─────────────┐
        │  dim_date   │  ◄── date_key (INT, YYYYMMDD)
        │             │      iso_year, iso_week, full_date, ...
        └──────┬──────┘
               │
               │ N:1
               ▼
        ┌─────────────────────┐         ┌──────────────┐
        │  fact_orders_line   │  ◄──N:1─│ dim_channel  │
        │                     │         │              │
        │ · order_line_id PK  │         │ channel_key  │
        │ · order_id          │         │ channel_     │
        │ · date_key   FK     │         │   source     │
        │ · channel_key FK    │         │ legacy_      │
        │ · product_key FK    │         │   channel_   │
        │ · quantity          │         │   group      │
        │ · line_price        │         │ is_paid      │
        │ · total_discount    │         └──────────────┘
        │ · _ingest_at        │
        └──────────┬──────────┘
                   │
                   │ N:1
                   ▼
            ┌──────────────┐
            │ dim_product  │
            │              │
            │ product_key  │
            │ sku          │
            │ vend_id      │
            │ item_descr   │
            │ season       │
            │ group, gender│
            │ class        │
            └──────────────┘
```

### 6.2 Grain declaration

`fact_orders_line` grain is **one row per Shopify order line item** (= one SKU instance on one order). This is the lowest meaningful grain for sales fact analysis and matches the legacy `Style_selling_df` grain. See `existing_data_inventory.md` §5.1.4 Insight #3 for why row-level grain is non-substitutable for this slice.

### 6.3 Key strategy

- **Surrogate keys** (`channel_key`, `product_key`) for all dimensions — INT, auto-incremented in seed/build scripts.
- **Smart date key** (`date_key` INT, YYYYMMDD) for `dim_date` — easier debug, no SCD on dates ever needed.
- **Natural business keys** (sku for product, channel_source for channel) kept as attribute columns for traceability.
- `-1` reserved in every dim for "unknown" / not-yet-mapped values, populated in seed step.

### 6.4 Table-level summary

| Table | Type | Rows (target) | Grain | Update Pattern |
|---|---|---|---|---|
| `dim_date` | Conformed dim | 2,922 (2023-01-01 to 2030-12-31) | 1 row per calendar date | One-time seed (Python script) |
| `dim_channel` | Conformed dim | ~16 | 1 row per TW channel_source | Seed SQL (versioned) + occasional ALTER |
| `dim_product` | Type 1 SCD | ~50K | 1 row per SKU | Daily full rebuild from ERS Volume + Shopify sku unique set |
| `fact_orders_line` | Transactional fact | ~10M (slice 1 window) | 1 row per order line item | Daily incremental append (later phase); slice 1 = full window rebuild |

---

## 7. ETL Module Breakdown (PySpark)

Four PySpark notebooks under `databricks-notebooks/slice_1/`. Each notebook is self-contained with: (a) idempotent re-runnability, (b) explicit input/output table list, (c) row count assertions, (d) elapsed time logging.

### 7.1 `01_build_dim_date.py`

**Input**: `dim_date.parquet` (uploaded by Sia to Volume from local Python script run).
**Output**: `mvdevdatabricks.analytics_platform_32degrees.dim_date`.

**Logic**: Read Parquet → assert row count = 2922 → write Delta with `mode("overwrite")`.

**Why Parquet over in-warehouse SQL date generation**: see Decision 11 — Python `datetime.isocalendar()` gives deterministic ISO 8601 boundary week behavior, while SQL date functions vary by dialect.

### 7.2 `02_seed_dim_channel.py`

**Input**: `docs/data_modeling/dim_channel_seed.sql` (already authored).
**Output**: `mvdevdatabricks.analytics_platform_32degrees.dim_channel`.

**Logic**: Execute the TRUNCATE-then-INSERT seed SQL → assert row count = 16 → log every distinct `legacy_channel_group` for visual inspection.

**Note**: This is *technically* a SQL operation, not PySpark — wrapped in a notebook for orchestration consistency (Phase 4 Workflows will treat all four notebooks uniformly).

### 7.3 `03_build_dim_product.py`

**Input**: latest `ers_product_master_*.csv` in Volume + distinct SKUs from `shopify_32degrees.order_line` for slice 1 window.

**Output**: `mvdevdatabricks.analytics_platform_32degrees.dim_product`.

**Logic** (key steps):
1. Read latest ERS CSV by filename suffix max.
2. Pull distinct skus from `order_line` (slice 1 window) using a broadcast-friendly small set.
3. Left join Shopify sku → ERS unique_identifier. For SKUs not matched, fall back: try matching on `item_description` (legacy pattern, see `legacy_panoply_etl.md` §2.3 Trick 2). If still not matched, assign `product_key = -1` and log to a quarantine table for later investigation.
4. Generate surrogate `product_key` using `monotonically_increasing_id()` + 1000-offset (reserves 0-999 for special values; -1 is in seed step).
5. Write Delta `mode("overwrite")`.

**Coverage target**: ≥ 99% of distinct active skus mapped to a real product. The 1% gap is acceptable for slice 1 demo and surfaces in DQ report.

### 7.4 `04_build_fact_orders_line.py` ⭐ (the technical meat)

**Input**: `order`, `order_line`, `attribution_order`, `attribution_order_click`, plus the three dim tables.

**Output**: `mvdevdatabricks.analytics_platform_32degrees.fact_orders_line`.

**Logic**: Detailed in §8 below — this is the cross-source join workhorse.

### 7.5 Execution order & dependencies

```
01_build_dim_date  ─┐
02_seed_dim_channel ├──► 04_build_fact_orders_line ──► DQ checks ──► metric SQL verify
03_build_dim_product┘
```

Notebooks 01/02/03 are mutually independent and can run in parallel. Notebook 04 hard-depends on all three dims being present (FK lookup logic).

---

## 8. Cross-source Join Strategy ⭐

This is Slice 1's most technically substantive section — the patterns established here propagate to slices 2+.

### 8.1 The join graph

```
shopify_32degrees.order_line  (one row per SKU on an order)
       │
       │  inner join on order_id
       ▼
shopify_32degrees.order        (one row per order — for processed_at timestamp)
       │
       │  left join on CAST(order.id AS STRING) = tw.attribution_order._triple_whale_order_id
       ▼
triple_whale.attribution_order (one row per order — for join key)
       │
       │  inner join on _triple_whale_order_id, filter attribution_model='last_touch'
       ▼
triple_whale.attribution_order_click (multiple rows per order, deduplicated to 1)
       │
       │  left join channel_source to dim_channel.channel_source
       ▼
dim_channel (channel_key resolution)

(separate join path)
order_line.sku ──► dim_product.sku ──► product_key

(separate join path)
date_trunc(order.processed_at - 5h, 'day') ──► YYYYMMDD ──► dim_date.date_key
```

### 8.2 Shopify ↔ TW order-level join

**Key challenge**: TW stores order ID as `_triple_whale_order_id` (STRING), Shopify stores it as `order.id` (BIGINT). Direct join fails on type mismatch.

**Solution**: `CAST(s.id AS STRING) = t._triple_whale_order_id`. Per `existing_data_inventory.md` §3.3, this is the standard pattern and yields ≥ 99.85% match.

**Unmatched orders**: ~0.15% (mostly very-recent orders not yet synced to TW). These get `channel_key = -1` (unknown) via left join → COALESCE, not dropped.

### 8.3 TW attribution model choice (Decision)

**Problem**: `attribution_order_click` contains rows for multiple `attribution_model` values per order (last_touch, linear, linearAll, etc.). Picking different models yields different channel attributions — and therefore different quantity-per-channel numbers.

**Slice 1 choice**: `attribution_model = 'last_touch'`.

**Rationale** (trade-off):
- ✅ Matches TW UI default — Leader and TW colleague see the same numbers in TW as in our portal, minimizing reconciliation friction during demo.
- ✅ Matches Panoply legacy attribution (GA4 default was last-click).
- ❌ Discards multi-touch insight (linear, position-based) — but this is out of slice 1 scope and revisitable in slice 4+ when ROAS gets multi-model treatment.

**Future evolution**: When slice 4 introduces ROAS, we will likely build `fact_attribution_touchpoint` at the touchpoint grain (preserving all models), letting the metric layer choose the attribution lens at query time. Slice 1's `fact_orders_line` carries only the resolved last-touch channel for simplicity.

### 8.4 Multi-touchpoint deduplication within `last_touch`

Even within `attribution_model = 'last_touch'`, an order may have multiple rows in `attribution_order_click` if the source data has been re-synced or if the model emits multiple position rows. To pick exactly one row per order:

```python
last_touch_per_order = (
    spark.table("mvdev_federated_catalog.triple_whale.attribution_order_click")
        .filter(F.col("attribution_model") == "last_touch")
        .withColumn(
            "rn",
            F.row_number().over(
                Window.partitionBy("_triple_whale_order_id")
                      .orderBy(F.col("position").desc_nulls_last(), F.col("click_date").desc_nulls_last())
            )
        )
        .filter(F.col("rn") == 1)
        .select("_triple_whale_order_id", "source")
)
```

**Why `position DESC, click_date DESC`**: `position` represents touchpoint ordering toward conversion; in last_touch model, the highest position is the conversion-adjacent touch. `click_date` is the tie-breaker for deterministic results.

### 8.5 Handling Non-attributed / Excluded channels (Decision 14)

Per Decision 14, the special channels `Non-attributed` and `Excluded` are **kept**, not filtered. In `attribution_order_click`, these appear as `source` values like `null-not-attributed` and `excluded` (TW UI naming may vary — confirm during Day 3 implementation). The dim_channel seed already contains rows for these so the left join resolves to a real `channel_key`. The frontend displays them with the same neutrality as TW UI.

### 8.6 ERS product join with graceful degradation

```python
# Primary: sku exact match
fact_with_product = order_line.join(dim_product, on="sku", how="left")

# Fallback: for unmatched, attempt item_description match
unmatched = fact_with_product.filter(F.col("product_key").isNull())
# (... fallback logic — full implementation in notebook 04)

# Final: assign -1 for still-unmatched, log to quarantine
```

This replicates the Panoply legacy pattern (see `legacy_panoply_etl.md` §2.3 Trick 2) — graceful degradation rather than dropping rows preserves quantity totals.

### 8.7 Timezone normalization

`order.processed_at` is UTC. The business operates in EST. Following the legacy convention (`legacy_panoply_etl.md` §2.3 Trick 10), the `date_key` is derived from `processed_at - 5h`. We use a fixed -5h offset (matches legacy) rather than DST-aware conversion for slice 1; DST nuance is documented as a known approximation (sub-1% impact on weekly aggregates).

### 8.8 Final fact_orders_line column derivation

| Column | Source |
|---|---|
| `order_line_id` | `order_line.id` (PK) |
| `order_id` | `order_line.order_id` |
| `date_key` | `INT(date_format(order.processed_at - INTERVAL 5 HOURS, 'yyyyMMdd'))` |
| `channel_key` | Resolved via TW last_touch dedup → dim_channel lookup |
| `product_key` | Resolved via sku → dim_product (with item_description fallback) |
| `quantity` | `order_line.quantity` |
| `line_price` | `order_line.price` (for slice 2 readiness) |
| `total_discount` | `order_line.total_discount` (for slice 2 readiness) |
| `_ingest_at` | `current_timestamp()` |

---

## 9. Data Quality Plan

Slice 1 reuses the YAML-driven DQ framework built in Track 3 (`metrics-service/data_quality/`). Four checks are configured for slice 1.

### 9.1 DQ checks

| Check | Type | Target | Threshold | Failure behavior |
|---|---|---|---|---|
| DQ-1: dim PK uniqueness | `unique` | All three dim tables' PKs | 100% unique | Pipeline fails, alert |
| DQ-2: fact FK referential integrity | `not_null` (against keys after resolution) | `fact_orders_line.{date_key, channel_key, product_key}` after COALESCE-to-(-1) | < 0.1% rows with -1 channel_key, < 1% with -1 product_key | Warning if exceeded, not fatal |
| DQ-3: fact freshness | `freshness` | `fact_orders_line._ingest_at` | max within last 36 hours | Warning |
| DQ-4: fact row count range | `range` | Slice 1 window total row count | Between 8M and 12M | Warning |

### 9.2 Reconciliation against Panoply legacy

This is the **trust-establishing** validation for Leader demo. Beyond automated DQ checks, run this comparison query at the close of Day 5:

```sql
-- New platform aggregate for last 7 complete days
WITH new_platform AS (
  SELECT d.iso_year, d.iso_week, p.vend_id, c.channel_source,
         SUM(f.quantity) AS qty
  FROM analytics_platform_32degrees.fact_orders_line f
  JOIN analytics_platform_32degrees.dim_date d ON f.date_key = d.date_key
  JOIN analytics_platform_32degrees.dim_product p ON f.product_key = p.product_key
  JOIN analytics_platform_32degrees.dim_channel c ON f.channel_key = c.channel_key
  WHERE d.full_date BETWEEN current_date() - INTERVAL 8 DAYS AND current_date() - INTERVAL 1 DAY
  GROUP BY ALL
),
panoply AS (
  -- Same shape from legacy Style_selling_df (run via Panoply connection)
  SELECT year AS iso_year, week AS iso_week, style AS vend_id, channelgrouping AS channel_source,
         SUM(quantity) AS qty
  FROM panoply.style_selling_df
  WHERE day BETWEEN current_date() - INTERVAL 8 DAYS AND current_date() - INTERVAL 1 DAY
  GROUP BY ALL
)
SELECT
  COALESCE(n.iso_year, p.iso_year) AS iso_year,
  ...
  n.qty AS new_qty,
  p.qty AS panoply_qty,
  ABS(n.qty - p.qty) / NULLIF(p.qty, 0) AS pct_diff
FROM new_platform n FULL OUTER JOIN panoply p USING (iso_year, iso_week, vend_id, channel_source)
WHERE ABS(COALESCE(n.qty, 0) - COALESCE(p.qty, 0)) > 0;
```

**Target**: 95% of (iso_week × vend_id × channel_source) buckets have `pct_diff < 2%`. The remaining 5% are expected to be channel-grouping translation differences (GA4 `Paid Search` ≠ TW `google-ads` exactly) — these are documented, not bugs.

### 9.3 DQ failure escalation

DQ failures during slice 1 dev are surfaced in the JSON DQ report (existing framework feature). Day 5 demo only proceeds if all checks pass. Phase 4 (orchestration) will wire failures to Slack alerts.

---

## 10. Performance Considerations

### 10.1 Delta Lake partitioning

| Table | Partition column | Rationale |
|---|---|---|
| `fact_orders_line` | `date_key` (INT) | Most slice 1+ queries filter by date range; partitioning by date is the canonical fact-table choice |
| All three dims | None | Small tables (< 100K rows); partitioning adds metadata overhead with no read benefit |

### 10.2 Z-ORDER

After initial build, run `OPTIMIZE fact_orders_line ZORDER BY (channel_key, product_key)`. The PBI page's drill-down matrix filters frequently on these two columns; Z-ORDER colocates related rows in files, reducing data scanned.

### 10.3 Broadcast join hints

All three dims are small (<100K). PySpark notebook 04 will hint:

```python
fact = fact.join(F.broadcast(dim_channel), ...)
fact = fact.join(F.broadcast(dim_product), ...)
fact = fact.join(F.broadcast(dim_date), ...)
```

Avoids shuffle on the large fact side.

### 10.4 Expected query latency

| Query pattern | Cold | Warm (Redis cache, future Phase 5) |
|---|---|---|
| Full year × all channels × top 50 styles | ~3-5s | N/A (cache target via Phase 5) |
| Single iso_week × single channel × all styles | < 1s | < 100ms |
| Single iso_week drill matrix (page default load) | < 2s | < 300ms |

Slice 1 success criterion is P95 cold load < 4s — well within the table above.

---

## 11. Schema Evolution & Rollback

### 11.1 Safe (additive) changes

- Adding nullable columns to any table → re-run ETL on the next schedule cycle.
- Adding new rows to seed-driven `dim_channel` → edit seed SQL, re-run notebook 02.
- Adding new metrics that read existing fact columns → no ETL change.

### 11.2 Changes requiring rebuild

- Grain change (e.g., changing fact_orders_line to order-level) → new table, deprecation of old.
- Adding SCD2 to dim_product → rebuild from version-controlled ERS history.
- Backfilling pre-2025-07-01 data → ETL window change + full fact rebuild.

### 11.3 Rollback procedure

Each notebook has a `DROP TABLE IF EXISTS` + recreate pattern controlled by a parameter `force_rebuild`. To roll back a bad build:

```python
# In notebook 04, set at top:
force_rebuild = True
# Pipeline drops the bad table and rebuilds from source. Delta time travel also available:
# RESTORE TABLE fact_orders_line TO VERSION AS OF <n>
```

Delta time travel provides additional safety net — table state at any prior version is reproducible without re-running ETL.

---

## 12. Metrics Layer Contract

### 12.1 YAML metric definition

File: `metrics-service/metrics/quantity_by_style_channel_week.yaml`

```yaml
name: quantity_by_style_channel_week
version: 1.0.0
description: |
  Total units sold per ISO week × style × channel, with optional drill-down
  to item_description (SKU level). Sourced from new Lakehouse fact_orders_line.
owner: sia.song
unit: units
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
      SUM(f.quantity) AS quantity
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
    date: 2026-05-19
    author: sia.song
    change: Initial slice 1 implementation. Maps from Panoply legacy
            Style_selling_df with GA4 → TW channel migration per Decision 8.
```

### 12.2 API endpoint contract

```
GET /metrics/quantity_by_style_channel_week
Query parameters:
  date_from   (ISO date, required)
  date_to     (ISO date, required)
  channels    (CSV, optional)
  seasons     (CSV, optional)
  vend_ids    (CSV, optional)

Headers:
  Authorization: Bearer <JWT>

Response (200):
{
  "metric": "quantity_by_style_channel_week",
  "version": "1.0.0",
  "data": [
    {
      "iso_year": 2026,
      "iso_week": 19,
      "vend_id": "PACKBAG",
      "item_description": "Packable Tote Bag",
      "channel_name": "google-ads",
      "legacy_channel_group": "Paid Search",
      "quantity": 1842
    },
    ...
  ],
  "_meta": { "row_count": 8421, "elapsed_ms": 1273 }
}
```

---

## 13. Frontend Wire-up

### 13.1 Visual ↔ API mapping

| Visual | Component | Data source |
|---|---|---|
| 1. Time slicer | `<DateRangeSlider />` | Sets `date_from` / `date_to`; no API call of its own |
| 2. Three filter slicers (channel / season / vend_id) | `<MultiSelect />` × 3 | One small "facets" API for available values (slice 1: derive from current data response); selection sets query params |
| 3. Channel quantity line chart | `<EChartsLine />` | Same metric API, grouped by `iso_year + iso_week` × `channel_name` |
| 4. Drill-down matrix | `<HierarchicalMatrix />` | Same metric API; client-side pivot for vend_id → channel → item_description hierarchy |

### 13.2 Filter state management

Single React Context holds filter state. URL query params mirror state (shareable links). Filter change → debounced API refetch (300ms).

### 13.3 Mock-first dev (recommended pre-permission)

In pre-permission Task F, the page is built end-to-end with a mock JSON response file (`frontend/mocks/quantity_by_style_channel_week.json`) shaped exactly like §12.2 response. Day 5 wire-up becomes literally toggling a `USE_MOCK` flag from `true` to `false` — no UI rework needed.

---

## 14. Testing Strategy

### 14.1 Unit-level (PySpark transformations)

Each notebook's pure-transformation functions (e.g., the last_touch dedup window, the sku → item_description fallback) are extractable to `databricks-notebooks/slice_1/lib/` and unit-testable with pytest + local SparkSession. Slice 1 ships at least 3 unit tests:

- Last-touch dedup keeps exactly one row per order, picks max(position).
- sku → product_key fallback hits item_description path when sku is null/missing in ERS.
- Date timezone derivation: `processed_at = 2026-01-01 03:00 UTC` → `date_key = 20251231`.

### 14.2 Integration smoke test (full pipeline)

End-of-Day-3 smoke: run all 4 notebooks against a 24-hour window (yesterday's data only) and assert non-zero row counts in all four tables. Catches catastrophic failures before full window run.

### 14.3 Reconciliation (§9.2)

Most important correctness check. Result captured as a CSV artifact committed to `docs/slice_1_reconciliation.csv` for the demo and future reference.

### 14.4 UI snapshot tests (deferred to slice 5+)

Slice 1 frontend changes are visually verified manually. Snapshot testing is added when the page count exceeds 3 and manual checking becomes lossy.

---

## 15. Deployment & Run Order

### 15.1 Pre-permission (current — covered by Pre-Day-2 task list)

1. ✅ Decision Log 10–16 documented in `PROJECT_CONTEXT.md` (Task A).
2. ✅ `generate_dim_date.py` smoke-tested locally (Task C).
3. ⏳ This design doc (Task B).
4. ⏳ Four PySpark notebook skeletons (Task D).
5. ⏳ YAML metric definition (Task E).
6. ⏳ Next.js page with mock data (Task F).
7. ⏳ DQ YAML configs (Task G).

### 15.2 Day 2 (= permission day)

```
1. Verify schema permission (test: CREATE TABLE / DROP TABLE in target schema)
2. Run star_schema_ddl.sql v1.1 → 4 empty tables created
3. Upload latest ers_product_master_YYYYMMDD.csv to Volume
4. Run scripts/generate_dim_date.py with --parquet, upload to Volume
5. Run notebook 01_build_dim_date     → assert rows = 2922
6. Run notebook 02_seed_dim_channel   → assert rows = 16
7. Run notebook 03_build_dim_product  → assert rows ≈ 50K, coverage ≥ 99%
8. Manual sanity: SELECT * FROM each dim table, eyeball 10 rows
```

### 15.3 Day 3

```
1. Run notebook 04_build_fact_orders_line (24-hour smoke window first)
2. Validate smoke output: row count > 0, all FKs resolve, no nulls in PK
3. Re-run notebook 04 over full slice 1 window (2025-07-01 → today)
4. Run OPTIMIZE fact_orders_line ZORDER BY (channel_key, product_key)
5. Run all 4 DQ checks → all PASS
```

### 15.4 Day 4

```
1. Swap mock Databricks client for real SQL connector in FastAPI
2. Wire JWT from existing auth (no change needed)
3. Add YAML metric file to metrics-service/metrics/
4. Manual test: GET /metrics/quantity_by_style_channel_week with various param combos
5. Assert response shape matches §12.2 contract
```

### 15.5 Day 5

```
1. Flip USE_MOCK=false in Next.js page
2. End-to-end test in browser: filters, drill-down, CSV export
3. Run reconciliation query (§9.2) → save CSV
4. Final DQ run → all PASS
5. Commit and push everything
6. Leader demo: walkthrough of (a) the page, (b) reconciliation CSV, (c) "what comes next"
```

---

## 16. Risks & Mitigations

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R1 | Permission grant delayed beyond 5 working days | Medium | High (delays demo) | All Task A–G prep work front-loaded → Day 2 onward is 4 days only, fully buffered. Follow-up email template at the ready. |
| R2 | TW `last_touch` rows have unexpected multiplicity (e.g., re-sync duplicates) | Medium | Medium | Dedup window function (§8.4) is deterministic. DQ check on `(_triple_whale_order_id, attribution_model)` uniqueness post-dedup catches anomalies. |
| R3 | Cross-year ISO week edge case (W52/W53) produces visible Leader-facing diff vs Panoply | Low | Medium | Document the difference proactively (`existing_data_inventory.md` §5.1.4 Insight #2 already covers); explain in demo as "intentional correction, not bug." |
| R4 | ERS upload missing or stale on Day 2 | Low | High (blocks dim_product) | Upload preparation included in Day 2 step 3 explicitly. Backup: re-use last month's CSV with warning surfaced in DQ. |
| R5 | Reconciliation diff > 2% threshold | Medium | High (erodes Leader trust) | Drill into the diff using the §9.2 query output. Most likely cause: channel taxonomy mismatch — known and explainable. Pre-prepare a 3-bullet explanation for the demo. |

---

## 17. Open Questions (deferred to Leader alignment)

These do **not** block slice 1 implementation but should be confirmed with Leader during or right after Day 5 demo:

1. **Channel grouping mapping**: `legacy_channel_group` mapping (TW `google-ads` → "Paid Search", `meta` → "Paid Social", etc.) is Sia's best-effort. Leader confirmation on the full 15-row table avoids later relabeling friction.
2. **Non-attributed / Excluded display**: Currently displayed inline with other channels (Decision 14). Leader may prefer them visually de-emphasized (gray) — easy frontend tweak.
3. **Refund handling on quantity**: Slice 1 displays gross quantity (no refund deduction), matching legacy `Style_selling_df` behavior. Slice 3 (refunds) will introduce `is_refunded` flag and a "net quantity" toggle — Leader's preference informs slice 3 priority.

---

## 18. Out of Scope (Slice 2+)

Explicitly listed to manage expectations during Day 5 demo:

- **Slice 2**: `Style-channel (revenue)` page. Reuses every table built in slice 1 + adds one YAML metric `revenue_by_style_channel_week`. Estimated 2–3 days.
- **Slice 3**: Refund analysis page. New tables `fact_refund_line`, `dim_refund_reason`. ~7 days.
- **Slice 4**: ROAS page. New table `fact_attribution_touchpoint` (multi-model), `fact_ad_spend`. ~5 days.
- **Phase 4**: Workflows orchestration + DQ alerting wiring + freshness SLAs.
- **Phase 4.5**: Real-time channel anomaly monitoring (Streaming).
- **Phase 5**: Redis caching, metrics catalog UI, lineage visualization.

---

## 19. Appendix

### A. Glossary

- **Conformed dimension**: A dimension table shared across multiple fact tables (Kimball term). `dim_date` and `dim_channel` are conformed across all future slices.
- **Grain**: The lowest-level "what does one row mean" of a fact table. Slice 1's grain is "one Shopify order line item."
- **SCD1 / SCD2**: Slowly Changing Dimension. Type 1 overwrites old values; Type 2 keeps history with effective dates.
- **YAGNI**: "You Aren't Gonna Need It" — design principle deferring complexity until proven necessary.
- **Last-touch attribution**: Attribution model giving 100% credit to the final touchpoint before conversion.
- **Z-ORDER**: Delta Lake feature colocating related data within files via multi-dimensional sort.
- **Vertical slice**: Deployment strategy where each iteration crosses every architectural layer end-to-end.

### B. References

- `NORTH_STAR.md` — project priority framework
- `PROJECT_CONTEXT.md` §5 (Decision Log) — Decisions 8, 9, 10–16 directly referenced in this doc
- `ROADMAP.md` — overall phase plan (this slice = part of Phase 2B/3)
- `PROGRESS.md` — running status; this slice's daily updates
- `docs/data_modeling/star_schema_ddl.sql` v1.1 — source of truth for table structure
- `docs/data_modeling/dim_channel_seed.sql` — dim_channel seed data
- `docs/existing_data_inventory.md` — §3 (TW), §5.1 (this PBI page reverse engineering), Appendix A (verification SQL)
- `docs/legacy_panoply_etl.md` — §2 (sales attribution legacy), §2.3 (the 6 join tricks reused here)
- `scripts/generate_dim_date.py` — dim_date seed generator
- `metrics-service/data_quality/` — DQ framework (Track 3 deliverable)

### C. Decision Log cross-reference

Decisions explicitly invoked in this design:
- **Decision 8**: TW must flow through Databricks → §5.2
- **Decision 9**: TW replaces GA4 attribution only → §2.2, §17
- **Decision 10**: Vertical slice methodology → §1.2
- **Decision 11**: ISO 8601 only date taxonomy → §2.2, §6.2, R3
- **Decision 12**: SCD1 with YAGNI deferred SCD2 → §3.2, §6.4
- **Decision 13**: Schema temporally unbounded, ETL window 2025-07-01+ → §3.1, §3.2
- **Decision 14**: Explicit meta-category modeling → §8.5
- **Decision 15**: Dual-display channel dimension → §6.1 (dim_channel structure)
- **Decision 16**: Forward-looking `is_paid` flag → §6.1 (dim_channel structure)

---

*End of Slice 1 Architecture Design Doc v1.0.*
