# Resume Highlights — 简历金句单一正源

> 投简历 / 面试前只看这一个文件。按主题组织,每条含可直接用的英文 bullet。
> 详细出处见各 daily log / decision log / completion summary。
> Last updated: 2026-06-04

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

- **✅ Three-mode auth behind one toggle (PAT / OAuth U2M / OAuth M2M)**: the M2M
  service-principal powers the headless container (U2M's browser consent can't run
  unattended). **Now running in production** — the deployed Azure Container Apps
  stack serves live data via the service principal. Connection reset-on-failure
  doubles as automatic token refresh.

## 8. 流程 / 方法论

- **Vertical-slice agile delivery**: end-to-end per PBI page, not waterfall —
  early stakeholder feedback, join-logic errors surface immediately.
- **Design-before-code**: authored 700-line Slice-1 + 750-line Phase-4
  architecture design docs before implementation.
- **Validate-before-acting**: read legacy source code to define semantics
  rather than guessing; same discipline caught the Appaman connector misconfig
  and TW backfill gaps within hours.

## 9. 编排 / 部署 / 增量 (Phase 4 + 6)

* **Production orchestration (Databricks Workflows)**: 7-task DAG with parallel
  dimension builds fanning into the fact, a quality gate, and a stakeholder
  digest — fan-out/fan-in dependency design with per-task retries and
  email-on-failure.

* **DQ-as-Gate, Spark-native**: the same versioned YAML check specs used for
  local unit testing are executed in Spark against the ~10M-row fact (cannot
  `.toPandas()`), gating downstream tasks; a hard failure fails the gate task
  and skips all consumers (fail-closed). Severity-calibrated (integrity → FAIL,
  domain/freshness → WARN) to avoid false blocks.

* **Validated fail-closed behavior via fault injection**: deliberately injected
  a failing check and confirmed the gate blocked and downstream tasks skipped —
  observability proven, not assumed.

* **Gate caught a real defect on first run**: surfaced a NULL `product_key`
  (an order line whose SKU was absent from the product master); fixed Kimball-
  correctly by adding a conformed Unknown member (surrogate key 0) and
  coalescing unmatched fact lookups to it, rather than allowing NULL FKs.

* **Config-as-code orchestration**: jobs defined as version-controlled JSON,
  deployed via the Databricks CLI — jobs are reproducible from the repo, not
  hand-built in the UI.

* **Incremental load with watermark + Delta MERGE**: converted the fact from
  full-overwrite to incremental upsert keyed on `shopify_line_id`, using
  Shopify `order.updated_at` as the watermark (bumped by refunds/edits, so
  late-arriving refunds are re-captured) with a 2-day lookback for sync lag;
  chose MERGE over partition-overwrite because refunds back-fill prior ISO-week
  partitions. Cuts a refresh from ~18 min (full) to seconds (incremental).

* **Backfill switch**: a single `FULL_REFRESH` flag toggles full-rebuild vs
  incremental in one pipeline — one source of truth plus on-demand backfill,
  instead of two parallel notebooks.

* **Operational runbook**: documented DAG, schedule, gate semantics, per-task
  failure response, and rerun/backfill procedures (Repair-run vs full run).

* **Pragmatic compute governance**: scheduled jobs run on a governed single-user
  cluster after the workspace disabled the cluster-creation entitlement and
  `.cache()` ruled out serverless — documented as an explicit trade-off
  (Decision 27), with the job-cluster config retained in git history.

* **Containerization**: multi-stage Docker builds for the Next.js frontend
  (standalone output) and FastAPI backend (uv), wired together with
  docker-compose for local end-to-end testing.

* **Infrastructure-as-Code (Terraform)**: Azure foundation — Container Registry,
  Key Vault (RBAC-authorized), Log Analytics, and a Container Apps environment —
  provisioned into a governed resource group, with cost-center tags on all
  resources for FinOps attribution.

* **Deployed to Azure Container Apps**: public external-ingress Next.js frontend +
  internal-ingress FastAPI backend (least-exposure, server-side proxy only).
  Images built cloud-side via `az acr build`.

* **Passwordless auth via one user-assigned managed identity**: the same identity
  provides `AcrPull` on the private registry and `Key Vault Secrets User` access —
  no registry passwords or secrets in any config.

* **Runtime Key Vault secret resolution**: app secrets are resolved at runtime from
  Key Vault via the managed identity, with no secret values stored in container
  definitions or environment-variable values.

* **Scale-to-zero / FinOps**: the frontend scales to zero when idle; the lightweight
  backend is kept warm with `min=1` to avoid cold-start latency on synchronous
  internal proxy calls — an explicit latency-vs-idle-cost trade-off.

* **Build-time vs runtime config discipline (Next.js)**: the browser-facing origin
  is baked at image build via `NEXT_PUBLIC_*`, while the backend URL is injected at
  runtime — avoiding frontend rebuilds whenever the backend address changes.

* **✅ Staged mock→live cutover**: validated the full cloud stack in mock mode first,
  then cut to live data via one env flip plus a Key Vault secret reference — the
  deployed app now serves real numbers from the Databricks Lakehouse.

## 10. 流式处理 (Phase 4.5 — real-time)

* **Auto Loader incremental file ingestion**: `cloudFiles` tailing a Unity Catalog
  Volume into streaming Delta tables, with an explicit schema + schema-location
  tracking (no inference guesswork).

* **Stream-stream join with watermark state-control**: ads ⟕ orders joined on
  `order_id` within a time-range condition; a **LEFT** join deliberately retains
  unmatched (no-conversion) ad spend so a ROAS crash can't be silently dropped —
  the watermark bounds join state so it can't grow unbounded.

* **Exactly-once + dedup**: checkpoints + the Delta sink give exactly-once;
  `dropDuplicatesWithinWatermark` upgrades an at-least-once source to
  effectively-once. Verified by killing and restarting the stream (no dup / no loss).

* **5-min sliding-window real-time anomaly detection**: per-channel ROAS windowed
  (5-min window, 1-min slide); a channel is flagged when ROAS drops below ~50% of
  its **own recent healthy baseline** (self-calibrating), not a brittle fixed threshold.

* **foreachBatch + Delta MERGE upsert**: each micro-batch applies the anomaly rule
  then upserts into a gold table — one row per (channel, window), updated live —
  the production pattern for streaming-to-curated-table writes.

* **流批一体 (batch/stream unification)**: a single `RUN_MODE` flag selects
  `trigger(availableNow=True)` (batch / backfill) vs `processingTime` (continuous)
  on the **same** Structured Streaming code — one logic, two execution modes.

* **Robust Delta streaming source**: reads upstream silver with
  `skipChangeCommits=true` so test-time table rewrites don't fail the stream.

* **Real-time dashboard**: Next.js + ECharts polling the serving API, with
  anomalous channels highlighted live.

## 11. 平台化 / 治理 (Phase 5)

* **Metrics Catalog (semantic layer / self-service discovery)**: an endpoint + page
  surfacing every metric's definition, grain, version, and changelog from the YAML
  DSL — one browsable source of truth for metric semantics.

* **Data lineage + impact analysis**: a source → silver → fact/dim → metric →
  dashboard DAG rendered as an interactive ECharts graph; clicking a node traces its
  full upstream + downstream (what a table change would impact).

* **Redis cache-aside layer**: metric results cached with a TTL keyed on
  metric + params, with **graceful degradation** (Redis unreachable → fall back to a
  direct query, never a hard dependency). Per-request latency on a cache hit drops
  from ~hundreds of ms to ~1 ms. *(Any cost-% claim is a cache-hit-rate estimate —
  labeled as such, no production traffic to measure real hit rate.)*

## 12. 成本 / ROI

* **Legacy warehouse cost optimization (~28%)**: cut Panoply spend from
  $2,499 → $1,799/mo (~$8.4K/yr run-rate) by tuning ingestion frequency and pruning
  unused tables on a volume-billed warehouse — owner-driven, fully substantiated.

* **Migration off per-seat BI**: replaced Panoply + 16 Power BI Premium-Per-User
  licenses (~$25K/yr legacy run-rate) with a self-built Databricks Lakehouse +
  self-service portal, removing per-seat licensing as a cost-to-scale.

* *(Integrity note: 16 users is the real, verifiable figure — do not inflate it.
  New-stack net savings to be finalized over a representative production month;
  Databricks is partly shared with a separate Costco workload, so allocate carefully.)*

---

## 待补(后续整理进上面)

- legacy_panoply_etl.md §0.2 的 13 个亮点(Multi-key resolution / Responsibility
  attribution model / REGEXP free-text extraction / PERCENTILE_CONT 等)还没并进来
- page_view #14 anti-bulk-bias 过滤 / #15 customer cohort classification
- ✅ Phase 4 + 6 已并入 §9;Streaming(4.5)已并入 §10;平台化(Phase 5)已并入 §11;成本已并入 §12

---

## STAR 面试故事(已成型的)

**Story 1: 对账证伪模型**
- S: 新平台 channel 销量比 legacy 系统性高 ~3%
- T: 不能盲目对齐 legacy(它本身有 bug),要找到真实口径
- A: 读 Panoply 源码定口径;发现自己最初的"整单排除 refund"模型让残差从 1.97%
  恶化到 6.57% → 推翻,重建为行级 netting;week-28 逐项拆解残差到每个因素
- R: −1.51% 过 trust gate,残差 100% 归因,顺带量化出 legacy 的 3 个精度缺陷

**Story 2: 无人值守容器连 Lakehouse (M2M)**
- S: 部署到 Azure 后,后端容器要连 Databricks,但 PAT 被禁、U2M 的浏览器授权在无人值守容器里跑不了
- T: 让 headless 容器安全地拿到 Databricks 访问权
- A: 用 service principal 走 OAuth M2M(client credentials);踩到"account 级 secret 必须先把 SP assign 到 workspace 才认"这个坑;先 mock 验证整栈,再一个 env flip + KV secret 引用切真数据
- R: 真数据在生产环境跑通,dashboard 显示真实数字;连接失败自动重置顺带刷新 token

**Story 3: 遗留仓成本优化**
- S: Panoply 涨价到 $2,499/mo,按数据量计费
- T: 在不影响业务的前提下降本
- A: 调整采集频率、按业务需求去重不必要的表采集 → 降低数据量
- R: 月费 $2,499 → $1,799(~28%,~$8.4K/yr run-rate),持续到迁移下线

(更多 STAR 见 legacy_panoply_etl.md §8.3)