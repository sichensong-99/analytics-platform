# Amazon FBA Receiving — Ingestion Completion Summary

> **Status**: ✅ Complete (data layer + scheduling + API + dashboard, end-to-end verified)
> **Date**: 2026-05-29
> **Domain**: Amazon FBA inbound receiving (second domain on the analytics platform)
> **Schema**: `mvdevdatabricks.analytics_platform_32degrees` (`amazon_` prefix isolation)

---

## 1. 目标与背景

把 Panoply 上的 Amazon FBA 入库数据迁到新平台,每周一 6am ET 自动更新,供 planning
同事跟进近期活跃 shipment 以制定补货/入库计划。

Amazon 与 Shopify/Triple Whale **无 join key**,是平台上的独立 domain。它把整个项目从
"单源(Shopify+TW)平台"升级为 **"多源、多 domain 平台"** —— 这是 Amazon 这条线最核心的
平台叙事价值。

对应 Panoply 的两个 connector + 一个 query model:

| Panoply 资产 | 新平台对应 | 角色 |
|---|---|---|
| connector `amazon_shipment_items` | notebook 01 → `amazon_silver_shipment_item` | 事实(shipment × SKU) |
| connector `amazon_shipments` | notebook 02 → `amazon_silver_shipment` | 维度(shipment 元数据) |
| query model `amazon_ship` | notebook 03 → `amazon_gold_receiving_by_sku` | items ⨝ shipments,对账视图 |

---

## 2. 架构

**Medallion(Bronze / Silver / Gold)**,三 notebook 在 Databricks Workflows 里编排成 DAG。

```
SP-API ──┐
         ├─ 01 items   → Bronze(append) → Silver(MERGE)  ┐
         │                                                ├─ 03 gold(overwrite,items ⨝ ships)
         └─ 02 ships   → Bronze(append) → Silver(MERGE)  ┘
```

**写模式(幂等设计)**:

| 层 | 写模式 | 重跑行为 | 理由 |
|---|---|---|---|
| Bronze | append | 累积原始 JSON | 审计 + replay;90 天 retention 控体积 |
| Silver | MERGE on grain | 同 grain 更新不新增 | 幂等;状态变化覆盖为最新 |
| Gold | overwrite | 全表重建 | 数据量小,永远是最新快照 |

**DAG 依赖**:最终为 `01 → 02 → 03`(串行)。02 依赖 01 的产出(见 §3 completeness 修复),
03 依赖 01 + 02。

**SP-API 工程**:LWA refresh-token 认证;指数退避重试 + `Retry-After` header + jitter
(封顶 60s);per-shipment 节流(0.8s);凭据存 Databricks Secrets(scope=`amazon`)。

---

## 3. 关键工程:两层 data-completeness 修复(Decision 25)

收口前的全量验证暴露了一个**两层 completeness 缺陷**,同一根因家族 —— 这是 Amazon 这条线
技术含量最高、面试最值得讲的部分。

### 根因:两个 SP-API feed 各自用日期窗口,但收货是分批陆续到的

两个 endpoint 都用 8 天 `LastUpdated` 窗口拉取。问题在于 FBA 收货分批到货,导致两个 feed
的"可见集合"不对称:

- **缺陷①(referential completeness)**:shipment 状态早已不变(几周前 CLOSED),落在
  shipments 窗口外;但其 item 收货量仍在更新,落在 items 窗口内。结果 67 个 item 行的
  shipment 维度缺失,gold 的 inner join **静默丢弃**了这些收货。
- **缺陷②(SKU-level completeness)**:同一 active shipment 内,最后更新早于 8 天的
  SKU 行被 items 窗口漏掉(样本 shipment `FBA19CRBL6RZ` 窗口只返回 12/20 个 SKU)。

### 修复

- **02 shipments → key-driven fetch**:从 `silver_item` 读 distinct `shipment_id`,用
  `ShipmentIdList` 按 ID 拉 shipments,保证每个 item 都能 join 上其 shipment。
- **01 items → 两段式 discover-then-hydrate**:
  - Stage 1 用 8 天 `DATE_RANGE` 窗口**仅发现活跃 shipment_id**(丢弃其 item 行,因为窗口会漏 SKU)。
  - Stage 2 对每个活跃 shipment 用 `GET /fba/inbound/v0/shipments/{id}/items`(无日期过滤、
    单页不翻页)拉**全量 SKU**。
- DAG 从 `01∥02→03` 改为 `01→02→03`(02 现依赖 01 产出)。

### SP-API 实战坑(踩坑记录)

- `/shipmentItems` 的 `QueryType` 只接受 `DATE_RANGE` / `NEXT_TOKEN`,**没有 `SHIPMENT` 取值**;
  取单 shipment 全量 item 必须走 path 形态 `/shipments/{id}/items`。
- 该 path endpoint **不能用 NextToken 翻页** —— 单次即返回全量,误翻页会把同样的行重复吐
  多页并触发 429 限流。
- 限流处理:`Retry-After` header + 指数退避 + jitter + per-shipment 节流。

### 验证(全量,非样本)

- `items_without_shipment`: 67 → **0**(全表)
- `FBA19CRBL6RZ`: 12 → **20** distinct SKU
- gold 行数: 191 → 258 → **826**(= item 全量数,逐步修复)

---

## 4. 范围决策:不做历史回填(Decision 26)

量化历史深度后发现:

| | 时间跨度 | shipment 数 |
|---|---|---|
| 新平台 gold | 2024-07 ~ 2026-05 | 21(近期活跃) |
| Panoply | 2022-10 ~ 2026-05 | 1363(3.5 年全量累积) |

表面看新平台"缺 98.5% 历史"。但核实业务用途后:**planning 同事用此数据跟进近期活跃
shipment 做前瞻性计划,不需要历史已定讫 shipment 的记录**(过去几年的死数据对补货计划无价值)。

**决策:不做历史回填。** 新平台的"发现窗口 → 只抓近期活跃 shipment"恰好匹配 planning 的
活跃视图需求,是**特性而非缺陷**。明确拒绝从 Panoply 搬全史(会污染活跃视图、增加维护负担、
灌入对用例无价值的死数据)。历史深度差异系**有意的范围裁剪,非数据丢失**。

---

## 5. 数据可信度结论(诚实分层)

Amazon 的数据可信度由三块组成,验证强度不同 —— 这里诚实标注每一块:

| 维度 | 验证强度 | 状态 |
|---|---|---|
| **口径逻辑正确性** | ✅ 强(源码级,与时间无关) | gold 逐行复刻 Panoply `amazon_ship`(inner join 键 / grain / 5 种 created_date 解析 / receiving_gap 公式);created_date unparsed=0(全表);gap 公式抽查全对 |
| **完整性 completeness** | ✅ 强(全量) | 全表 `items_without_shipment=0`;每个活跃 shipment 走全量 SKU 拉取(§3) |
| **数值同时刻对账** | ⚠️ 无法强验,已诚实标注 | 见下 |

**数值对账为何无法做**:Panoply 于 **2026-05-18 冻结**,与新平台实时状态相隔 11 天,
**缺少同时刻基线**。逐行比对会被冻结噪音淹没(大量"对不上"实为冻结造成,非口径 bug)。
抽查样本 `FBA19CRBL6RZ` 印证了这一点:新平台 received 为到仓终值(60/59/61),Panoply 同
shipment received 全为 0、status=IN_TRANSIT(冻结时点的在途快照)。差异方向符合预期 ——
**新平台同时更全(20 SKU)且更新(到仓终值)**,是"修正 legacy 过期快照"的实证。

由于已确认新平台本就不应包含历史已定讫 shipment(§4),"挑老 CLOSED shipment 对账"的方案
前提也不成立,故数值对账跳过,改以源码级口径 + 全量 completeness 保证可信度。

> 这个结论比"全量对账通过"更扛面试追问:它体现的是"知道什么能验证、什么不能,不在无效对比
> 上硬凑结论,并能讲清原因"——这是高级工程师的判断力。

---

## 6. 交付物

**数据层**:
- `01_ingest_shipment_items.py`(两段式 discover-then-hydrate)
- `02_ingest_shipments.py`(key-driven fetch)
- `03_gold_receiving_by_sku.py`(items ⨝ shipments + created_date 解析 + receiving_gap)
- Databricks Job `amazon_shipment_ingestion_weekly`(01→02→03,周一 6am ET)

**服务层**:
- `metrics-service`: `/snapshot/{metric_id}` 端点(无 date,区别于 `/metrics` 时间序列)
- `definitions.yaml`: `amazon_fba_receiving_by_sku` 指标
- `databricks_client.py`: Amazon mock 分支 + `LIST_GUARD_PARAMS` 扩展(statuses/fcs)

**前端**:
- `dashboards/amazon-shipments/page.tsx`(表格 + KPI + status/FC filter + CSV export)
- `api/snapshot/[metricId]/route.ts` proxy
- dashboards 列表页 Amazon 卡片

**端到端验证**:真连冒烟测 `/snapshot/amazon_fba_receiving_by_sku` 返回 **826 行**
(Lakehouse gold → FastAPI OAuth 真连 → API 全链路打通)。

**文档**:
- `docs/architecture/amazon_ingestion_design.md`
- 本文档 `docs/architecture/amazon_completion_summary.md`
- PROJECT_CONTEXT Decision 23 / 24 / 25 / 26
- `star_schema_ddl.sql` 含 `amazon_gold_receiving_by_sku` DDL

---

## 7. 简历关键词

- **Multi-source / Multi-domain Platform** — 在统一平台上以 prefix 隔离接入第二个独立 domain
- **Custom SP-API Ingestion** — 非托管 connector,自建 LWA 认证 + 分页 + 限流 + 重试
- **Referential Completeness** — fact-key 驱动 dimension 拉取,inner join 不丢数
- **SKU-level Completeness / Two-stage Discover-then-Hydrate** — 窄窗发现 + per-key 全量拉取
- **Cross-feed Window Skew** — 诊断两个异构 feed 的时间窗口不对称
- **SP-API Throttling / Backoff** — Retry-After + 指数退避 + jitter + 节流
- **Idempotent Medallion** — append Bronze + MERGE Silver + overwrite Gold
- **Scope-driven Data Modeling / Business-aligned Retention** — 按业务用途裁剪数据范围而非无脑全量迁移
- **Legacy Snapshot Correction** — 新平台数据较冻结的 legacy 更全更新,诚实标注对账局限