# Slice 1 Completion Summary — Style × Channel Quantity

**Slice**: 1 of N
**Status**: ✅ Complete (pending metafield-driven replacement exclusion rerun)
**Completion Date**: 2026-05-27
**Duration**: ~9 days end-to-end (Day 1-5 planned + Day 6-9 reconciliation iteration)

---

## 1. Objective

Migrate the legacy BI `Style-channel (quantity)` page to the new platform
end-to-end: Shopify + Triple Whale → Databricks Kimball star schema → FastAPI
metrics service → Next.js portal, with quantitative reconciliation against the
legacy Panoply pipeline as the trust gate.

---

## 2. Deliverables

### 2.1 Data Warehouse Layer
- 1 fact table (`fact_orders_line`, 9.97M rows, partitioned by iso_year+iso_week)
- 3 conformed dimensions (`dim_date`, `dim_channel`, `dim_product`)
- 4 PySpark notebooks (01-04, full rebuild + Phase 4 incremental path designed)
- DDL synced to actual production tables (`docs/data_modeling/star_schema_ddl.sql` v2.0)

### 2.2 Metrics Service
- `quantity_by_style_channel_week` v1.2 YAML-defined metric
- FastAPI service running OAuth U2M to Databricks SQL Warehouse
- JWT auth, query param binding, IN-clause safety

### 2.3 Frontend
- Next.js `style-channel-quantity` page wired to live API
- ISO week selector, channel/season/style filters, CSV export

### 2.4 Reconciliation
- 2 SQL queries (Panoply BigQuery + Databricks)
- Python diff script with PASS/WARN/FAIL/MISSING classification
- Excel report generator with color coding
- Week-28 reconciliation result: −1.51% overall, fully itemized residual

### 2.5 Documentation
- Slice 1 architecture design (~700 lines, 19 sections)
- Phase 4 orchestration design (~750 lines)
- Reconciliation methodology document
- Legacy Panoply ETL reverse-engineering documentation
- 22 architectural decisions logged (Decision 10-22 v3)

---

## 3. Architectural Decisions Locked

| # | Decision | Key takeaway |
|---|---|---|
| 10 | Vertical Slice methodology | End-to-end per page, not waterfall layer-by-layer |
| 11 | ISO 8601 only, drop US-week | Single date taxonomy |
| 12 | SCD1 for v1 (YAGNI) | SCD2 deferred until justified |
| 13 | Schema temporally unbounded | ETL window in WHERE, not schema |
| 14 | Channel meta-categories explicit | Non-attributed / Excluded modeled, not dropped |
| 15→21 | channel_group as roll-up hierarchy | Repositioned from GA4-compat to Kimball drill |
| 16 | Forward-looking `is_paid` flag | Pre-encode for slice 4+ ROAS |
| 17 | DST-aware America/New_York timezone | Corrects legacy `processed_at - 5h` bug |
| 18 | Multi-tier DQ SLO with empirical baseline | 0.5%/2% calibrated from 0.15% baseline |
| 19 | ERS dual-schema auto-detection | Backward compatible ingest |
| 20 | Shared raw zone for ERS | Conformed reference data architecture |
| 22 v3 | Materialized business rules | EXC+replacement = is_sales_attributable; refund = line-level netting |

---

## 4. Quantified Results

Key headline numbers:
- **Scale**: ~10M order lines processed in slice 1 ETL window
- **Reconciliation**: −1.51% overall (< 2% trust gate)
- **Residual attribution**: 100% itemized
- **Channel DQ**: 0.318% unmatched (PASS, baseline 0.15%)
- **Product DQ**: 0.000% (PASS)
- **Legacy accuracy gap exposed**: tag-reverse-engineered refund coverage = 22%

---

## 5. Engineering Highlights

### 5.1 Modeling
- **Cross-source heterogeneous-type join**: Shopify `order_line.order_id` (BIGINT)
  ↔ TW `_triple_whale_order_id` (STRING) with explicit cast normalization,
  99.72% match rate.
- **Last-touch attribution dedup via window function**:
  `row_number() over (partition by tw_order_id order by position DESC, click_date DESC)`.
- **Multi-grain Kimball modeling**: line-level fact for SKU drilldown; order-level
  fact reserved for slice 2 channel aggregation.

### 5.2 Data Quality
- **Multi-tier SLO** (PASS/WARN/FAIL) calibrated to empirical 0.15% baseline,
  avoiding alert fatigue.
- **DQ-as-Gate pattern**: FAIL threshold halts pipeline before write — bad data
  never reaches downstream consumers.
- **Source value normalization layer**: case-insensitive `emarsys` → `Emarsys`,
  URL-encoded `google%...` → `google-ads`.

### 5.3 Reconciliation
- **Reconciliation-driven model correction**: order-level refund exclusion
  disproven by reconciliation (residual 1.97% → 6.57%), rebuilt as line-level
  net deduction.
- **Fully-itemized residual attribution**: 2,880 unit gap explained as
  EXC 2209 + refund 6573 + cancel 803, no "noise" hand-waving.
- **Quantified legacy accuracy gap**: legacy tag-based refund detection covered
  only 22% of native refunds; new platform uses Shopify native refund table for
  100% coverage.
- **Cross-dialect SQL forensics**: identified Panoply runs on BigQuery backend
  from source-code patterns, switched reconciliation SQL to `EXTRACT(ISOYEAR FROM day)`.

### 5.4 Architecture
- **Business rule materialization**: `is_sales_attributable` boolean column
  encodes the "is this row channel-attributable sales?" rule once at the data
  layer, replacing 4 scattered WHERE filters in legacy Panoply pipelines.
- **Versioned metrics with breaking-change annotation**:
  `quantity_by_style_channel_week` v1.1 → v1.2 explicitly marked breaking
  (gross → net semantics).
- **Fault-tolerant ETL with auto-detection**: replacement signal detection
  auto-detects `order_metafield` table availability and degrades gracefully
  when not yet synced — zero code change needed at activation.
- **DST-aware timezone handling**: `from_utc_timestamp('America/New_York')`
  corrects legacy `processed_at - 5h` bug that systematically miscounted
  summer EDT cross-midnight orders.

### 5.5 Schema Evolution
- **ERS dual-schema ingest**: auto-detects legacy (`Unique_Identifier`/`Vend_ID`)
  vs current (`SKU`/`Style#`/`Item Description`) formats, normalizes to unified
  internal schema — historical CSVs replayable without rewriting.

---

## 6. Open Items (carry into Slice 2 / Phase 4)

| Item | Trigger | Owner |
|---|---|---|
| Replacement exclusion rerun | order_metafield sync completes | platform owner |
| Reconciliation refresh post-replacement | After above | platform owner |
| Stakeholder demo + feedback | Demo script complete | platform owner |
| Slice 2 (revenue page) | Demo feedback | platform owner |
| Slice 2 backlog: order-grain fact | Slice 2 modeling | platform owner |
| TW Web Analytics ingestion | Databricks team | external |

---

## 7. Lessons Learned

### 7.1 Validate before acting
The −2,880 unit gap was solved by reading Panoply source code, not by guessing.
This pattern caught two earlier blocking issues (a Shopify connector misconfigured
to point at the wrong source store, and insufficient TW historical data) within
hours.

### 7.2 Reconciliation as model correctness oracle
Reconciliation isn't just a trust-building artifact for stakeholders — it actively
corrected the `is_sales_attributable` model. Without the residual worsening
from 1.97% to 6.57%, the order-level refund exclusion would have shipped
silently incorrect.

### 7.3 Trust gate > zero-diff
Pursuing 0% diff against legacy Panoply would have meant reproducing legacy
bugs (DST drift, cancel-as-sale, 78% refund undercoverage). The discipline
of "< 2% overall AND fully itemized residual" preserves new-platform
correctness while keeping the migration auditable.

### 7.4 Graceful degradation > blocking on upstream
The replacement signal could not block Slice 1 delivery. Auto-detection of
table availability + degrading to FALSE keeps the pipeline running and the
upgrade trivial once the upstream sync completes.
