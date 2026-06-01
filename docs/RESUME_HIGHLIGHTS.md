# Resume Highlights — 简历金句单一正源

> 投简历 / 面试前只看这一个文件。按主题组织,每条含可直接用的英文 bullet。
> 详细出处见各 daily log / decision log / completion summary。
> Last updated: 2026-05-28

---

## 0. 项目级 Headline

> Designed and built an end-to-end internal data platform replacing Power BI
> Service for an apparel brand's ecom team — multi-source Lakehouse ingestion,
> Kimball dimensional modeling, a versioned YAML-driven metrics service, and a
> self-service Next.js portal — delivered via vertical-slice methodology with
> quantitative reconciliation against the legacy system as the trust gate.

规模数字(STAR 的 R):~10M order lines processed, 25M+ TW attribution events
scanned, reconciliation −1.51% with 100% itemized residual.

---

## 1. 数仓建模 (Kimball)

- **Cross-source heterogeneous-type join**: Shopify `order_line.order_id`
  (BIGINT) ↔ Triple Whale `_triple_whale_order_id` (STRING) with explicit cast
  normalization, achieving 99.72% match rate across ~10M rows.
- **Last-touch attribution dedup via window function**:
  `row_number() over (partition by tw_order_id order by position DESC, click_date DESC)`.
- **Multi-grain modeling** (Kimball "don't pre-join across grains"): line-grain
  fact for SKU drilldown; order-grain fact reserved for channel aggregation.
- **Conformed dimension design**: single `dim_date` (ISO 8601) serving all facts,
  replacing two duplicate DAX calendar tables in the legacy PBI report.
- **Roll-up hierarchy**: `channel_source` (24 detail) → `channel_group`
  (~10 exec-level), a Kimball drill-down path (repositioned from "GA4 compat").

## 2. 数据质量与对账

- **Multi-tier DQ SLO** (PASS/WARN/FAIL) calibrated against empirical 0.15%
  baseline, avoiding alert fatigue (SRE-style observability).
- **DQ-as-Gate pattern**: FAIL threshold halts the pipeline before write — bad
  data never reaches downstream consumers.
- **Reconciliation-driven model correction**: order-level refund exclusion
  disproven by reconciliation (residual worsened 1.97% → 6.57%), rebuilt as
  line-level net deduction.
- **Fully-itemized residual attribution**: the 2,880-unit gap explained as
  EXC 2,209 + refund 6,573 + cancel 803 — no hand-waved "noise".
- **Quantified legacy accuracy gap**: legacy tag-based refund detection covered
  only 22% of native refunds; identified cancelled orders miscounted as sales.
- **Trust gate over zero-diff**: redefined gate as "overall < 2% AND fully
  itemized residual" instead of "95% buckets pass", avoiding small-denominator
  distortion.
- **Cross-dialect SQL forensics**: identified the legacy system runs on a
  BigQuery backend from source-code patterns; switched reconciliation SQL to
  `EXTRACT(ISOYEAR FROM day)`.

## 3. 业务规则物化 / 语义层

- **Business rule materialization**: `is_sales_attributable` boolean encodes the
  "is this row channel-attributable sales?" rule once at the data layer,
  replacing 4 scattered WHERE filters in legacy pipelines.
- **Restock-type-aware line-level refund netting**: `refunded_quantity` sums
  `order_line_refund.quantity` across all restock types (return / no_restock /
  cancel / legacy), net units = quantity − refunded_quantity.
- **Versioned metrics with breaking-change annotation**:
  `quantity_by_style_channel_week` v1.1 → v1.2 explicitly marked breaking
  (gross → net semantics).

## 4. 工程缺陷修正 (legacy bug correction)

- **DST-aware timezone**: `from_utc_timestamp('America/New_York')` corrects
  legacy static `processed_at - 5h` that systematically miscounted summer EDT
  cross-midnight orders (~1% drift).
- Documented as intentional corrections in the migration (3 total: DST drift,
  22% refund undercoverage, cancel-as-sale).

## 5. Schema 演进容错

- **ERS dual-schema ingest**: auto-detects legacy (`Unique_Identifier`/`Vend_ID`)
  vs current (`SKU`/`Style#`) formats, normalizes to a unified internal schema —
  historical CSVs replayable without rewriting.
- **Fault-tolerant ETL with auto-detection**: replacement-signal detection
  auto-detects `order_metafield` table availability and degrades gracefully when
  not yet synced — zero code change needed at activation.

## 6. API Ingestion / Medallion (Amazon domain)

- **REST API ingestion** of Amazon SP-API: OAuth LWA refresh-token auth,
  exponential-backoff retry on 429/5xx, token-based pagination.
- **Medallion Bronze/Silver/Gold** on Delta Lake: schema-on-read Bronze (raw
  JSON, 90-day replay retention), schema-on-write Silver (typed + DQ gate),
  Gold business view.
- **Idempotent MERGE upsert** on grain with an 8-day window + 1-day overlap —
  re-runnable without duplication.
- **Multi-domain platform with prefix isolation**: Amazon (no join key with
  Shopify/TW) modeled as an independent domain in the same schema via `amazon_`
  prefix — sharing metric service, portal, DQ framework, and orchestration,
  while data stays isolated. Demonstrates judgment on when to conform vs isolate.
- **Source-extensible platform**: new source absorbed following the same
  patterns without re-architecture.
- **Workload-aware compute selection**: cache-heavy Slice-1 ETL on classic
  compute; lightweight Amazon ingestion on serverless (saves cold start).
- Diagnosed and fixed a two-layer data-completeness defect in a custom Amazon SP-API
  ingestion pipeline: a date-windowed pull silently dropped both shipment-dimension rows
  and older SKU lines of still-active shipments. Re-architected to a two-stage
  discover-then-hydrate pattern (windowed discovery → per-key full pull) plus fact-key-driven
  dimension fetch, restoring referential + SKU-level completeness (gold rows 191 → 826) and
  surfacing fresher receiving figures than the frozen legacy BigQuery snapshot.

## 7. 架构 / 服务化

- **Data serving layer**: standalone FastAPI metrics service decoupling metric
  definition from consumption (vs Next.js querying the warehouse directly).
- **YAML-driven metric DSL**: new metrics with zero code changes.
- **Time-series vs snapshot query patterns**: distinct `/metrics/{id}`
  (date-windowed) and `/snapshot/{id}` (current-state) endpoints.
- **mock/databricks dual-mode client**: frontend dev & demo unblocked when the
  warehouse is unavailable (proved its value during a SQL-access outage).
- **OAuth U2M auth** to Databricks SQL Warehouse after org disabled PATs;
  connection caching to avoid re-auth on every query.

## 8. 流程 / 方法论

- **Vertical-slice agile delivery**: end-to-end per PBI page, not waterfall —
  early stakeholder feedback, join-logic errors surface immediately.
- **Design-before-code**: authored 700-line Slice-1 + 750-line Phase-4
  architecture design docs before implementation.
- **Validate-before-acting**: read legacy source code to define semantics
  rather than guessing; same discipline caught the Appaman connector misconfig
  and TW backfill gaps within hours.

---

## 待补(后续整理进上面)

- legacy_panoply_etl.md §0.2 的 13 个亮点(Multi-key resolution / Responsibility
  attribution model / REGEXP free-text extraction / PERCENTILE_CONT 等)还没并进来
- page_view #14 anti-bulk-bias 过滤 / #15 customer cohort classification
- Phase 4 / 4.5 / 5 / 6 完成后的关键词(Workflows / Streaming / Redis / FinOps)

---

## STAR 面试故事(已成型的)

**Story: 对账证伪模型**
- S: 新平台 channel 销量比 legacy 系统性高 ~3%
- T: 不能盲目对齐 legacy(它本身有 bug),要找到真实口径
- A: 读 Panoply 源码定口径;发现自己最初的"整单排除 refund"模型让残差从 1.97%
  恶化到 6.57% → 推翻,重建为行级 netting;week-28 逐项拆解残差到每个因素
- R: −1.51% 过 trust gate,残差 100% 归因,顺带量化出 legacy 的 3 个精度缺陷

(更多 STAR 见 legacy_panoply_etl.md §8.3)