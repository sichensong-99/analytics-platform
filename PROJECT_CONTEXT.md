# Project Context: Internal Analytics Platform

> 这份文档是项目的"宪法"——任何新 chat 开始时,先读这份。

---

## 1. 项目背景

**起因**:公司原本用 Power BI Service 给团队展示 dashboard,每人 $20/月订阅费,Leader 觉得贵,要求做一个内部网页应用替代,团队登录就能看 dashboard。

**作者**:Sia(Sia Song,GitHub: sichensong-99)

**Leader 要求**:
- 一个网页应用,看起来像"我们自己做的产品"
- 能展示 dashboard,替代 PBI Service
- 能下载数据
- 团队所有人都能用

**作者的隐藏目标**:把这个项目做成回国找 Data Engineer 工作的核心简历项目,所以不止做"网页",而是做一个**端到端的数据平台**。

---

## 2. 数据源

| 数据源 | 状态 |
|---|---|
| Shopify 订单数据(`shopify_32degrees`) | ✅ Ready(Fivetran,11.45M 订单) |
| Triple Whale 归因(`mvdev_federated_catalog.triple_whale`) | ✅ Ready(全月 ≥99.85% match) |
| ERS 产品主数据 | ✅ 月度 CSV 上传至共享 raw zone(Decision 20) |
| Amazon FBA 入库(SP-API) | ✅ 自建 ingestion(Decision 23/24) |

**关键决策**:Triple Whale **走 Databricks**,不直接进应用层。理由:
- 跨源分析需要在统一数据层关联(订单 + 归因)
- 整合多源 SaaS 数据进 Lakehouse 是 DE 简历核心素材
- 直连应用会丢失这块工作

---

## 3. 最终架构
┌─────────────────────────────────────────────┐
│  Next.js (Frontend Portal)                  │
│  · Dashboard Portal                          │
│  · Metrics Catalog                           │
│  · Lineage Visualization                     │
│  · JWT Auth + CSV Export                     │
└─────────────────────────────────────────────┘
↓ HTTP
┌─────────────────────────────────────────────┐
│  FastAPI (Metrics Service)                  │
│  · RESTful Metrics API                       │
│  · Redis Cache                               │
│  · Auth & Param Validation                   │
└─────────────────────────────────────────────┘
↓ Load
┌─────────────────────────────────────────────┐
│  Metric Layer (YAML-driven DSL)             │
│  · Metric Definitions + SQL Templates        │
│  · Owner / Unit / Lineage Metadata           │
│  · Versioning + Changelog                    │
└─────────────────────────────────────────────┘
↓ SQL
┌─────────────────────────────────────────────┐
│  Databricks Lakehouse                       │
│  · DWS (Aggregated Metrics)                 │
│  · DWD (Fact + Dimension Tables, Kimball)   │
│  · ODS (Raw: Shopify, Triple Whale)         │
└─────────────────────────────────────────────┘
↑ Orchestrate
┌─────────────────────────────────────────────┐
│  Databricks Workflows                       │
│  · DAG: ODS → DWD → DWS                     │
│  · Data Quality Framework (YAML-driven)     │
│  · Failure Alerts                           │
└─────────────────────────────────────────────┘
外加 Phase 4.5:Real-time module via Auto Loader + Structured Streaming
---

## 4. 技术栈(已锁定)

| 层 | 技术 | 选型理由 |
|---|---|---|
| 前端 | Next.js 16 + TypeScript + Tailwind | 全栈一体、部署简单、TS 类型安全 |
| 图表 | Apache ECharts | 开源、国内大厂主流、面试加分 |
| 后端服务 | FastAPI + Pydantic | 自动文档、性能好、Python 生态 |
| 包管理 | uv | 比 pip 快几十倍,国内大厂趋势 |
| 鉴权 | JWT (python-jose / jsonwebtoken) | 前后端共享 secret 实现互通 |
| 指标定义 | YAML DSL (PyYAML) | 配置驱动,新增指标 0 代码 |
| 数据仓库 | Databricks Lakehouse + Delta Lake | 公司已有,ACID + Time Travel |
| 数仓建模 | Kimball 维度建模 | 业务分析标准方案 |
| 调度 | Databricks Workflows | 与 Lakehouse 深度集成 |
| 缓存 | Redis | 降低 SQL Warehouse 成本 |
| 流处理 | Auto Loader + Structured Streaming | 不用搭 Kafka,难度可控 |
| 部署 | Vercel(前端)+ 公司服务器(后端,待定) | 免费起步 |

---

## 5. 关键决策记录(Decision Log)

> 这里记录所有"为什么这么选"的理由,面试时就靠这些讲故事。

### Decision 1:架构上加独立 FastAPI 服务层(而不是 Next.js 直连 Databricks)
- **日期**:Phase 2A 设计时
- **理由**:解耦数据消费与存储,统一指标口径,实现"数据服务化"
- **关键词**:Data Serving Layer / Metric Platform / Single Source of Truth

### Decision 2:指标用 YAML DSL 配置(而不是写死 SQL 在代码里)
- **日期**:Phase 2A 设计时
- **理由**:新增指标 0 代码改动;指标定义和消费解耦;支持版本管理
- **关键词**:Configuration-Driven / Metric Governance

### Decision 3:每个指标加 version + changelog
- **日期**:Phase 2A 设计时
- **理由**:指标口径会变,需要追踪历史;支持 breaking change 标记
- **关键词**:Versioned Metrics / Schema Evolution

### Decision 4:数据接入前先写 Data Contract
- **日期**:Phase 1
- **理由**:让前端可以并行开发;明确上下游协作标准;Data Mesh 思想
- **关键词**:Data Contract / Schema Governance / Data as a Product

### Decision 5:不做 Airflow,只用 Databricks Workflows
- **日期**:规划阶段
- **理由**:单一数据源场景下 Workflows 已足够,Airflow 会喧宾夺主
- **面试时怎么解释**:"如果是多源异构(Databricks + Snowflake + 外部 API)我会选 Airflow"

### Decision 6:Phase 4.5 加实时模块(渠道异常监控)
- **日期**:实时方案讨论后
- **理由**:增加 streaming 关键词,冲一线大厂中高级岗
- **范围**:仅做"实时渠道异常监控"单一场景,5-7 天

### Decision 7:不做"国内+海外"双壳配置
- **日期**:求职策略讨论
- **理由**:国内招聘官只看关键词,双壳显得"什么都浅"
- **正确做法**:一份项目,投不同公司时换简历关键词

### Decision 8:Triple Whale 必须走 Databricks
- **日期**:数据流向讨论
- **理由**:跨源分析价值;整合多源是 DE 核心活儿;直连应用会丢简历素材

### Decision 9:TW 替代 GA4 仅限 attribution layer
- **日期**:2026-05-18(发现于同事 Page_view 需求分析)
- **背景**:TW 以"订单"为锚点(只跟踪下单),GA4 以"用户行为"为锚点(跟踪所有访问)
- **结论**:TW 替代 GA4 仅覆盖 attribution(channel × revenue / ROAS / 订单归因),不覆盖 funnel metrics(page view / add to cart / sessions)
- **影响**:新平台 Phase 2B/3 完成后,需 revisit 数据源边界是否纳入 GA4 / Shopify Analytics 以支持 funnel 分析
- **关键词**:Data Source Boundary / Attribution vs Funnel / SaaS Platform Capability Mapping
v2 注(2026-05-26):TW 同事确认 TW Web Analytics 表覆盖 funnel(page view / add to cart / session),TW 对 GA4 的替代范围比原判断更宽;但渠道分组为平台型,与 GA4 功能型 15 类口径不一致,page_view 迁移需做渠道映射。

### Decision 10:Phase 2B/3 采用 Vertical Slice(垂直切片)方法论交付
- **日期**:2026-05-18
- **背景**:传统瀑布式做法是先把所有 fact/dim 表建完,再做服务层,最后做前端。这样的问题是要等很久才能给 Leader 看到东西,而且如果中间环节有问题(比如 join 逻辑错),会发现得很晚。
- **结论**:采用 vertical slice — 每个切片从数据源到前端端到端打通一个 PBI page,逐切片扩展数仓。切片 1 服务 `Style-channel (quantity)` page,5 天完整交付。
- **Trade-off**:
  - ✅ 早期就能给 stakeholder 看到真实成果,获取反馈
  - ✅ 每个切片都是端到端,数据流路径上的问题早暴露
  - ✅ 切片 2+ 可复用切片 1 的 fact/dim,边际成本递减
  - ❌ 需要在每个切片做"端到端打通"工作,初期看似多花时间
- **关键词**:Vertical Slice Delivery / MVP-first / Iterative Stakeholder Feedback / Agile Data Platform Delivery

### Decision 11:Date taxonomy 用 ISO 8601 only,不保留 US-week 兼容字段
- **日期**:2026-05-18
- **背景**:Panoply 旧表里同时存在 ISO 8601 周(周一为首日)和 US-week(周日为首日)两种口径。新平台是否要保留两套以兼容旧报表?
- **结论**:只保留 ISO 8601。Panoply 旧报表口径不正确(跨年周可能算错),没必要兼容。
- **Trade-off**:
  - ✅ 单一 source of truth,所有时间维度查询走 dim_date.iso_year / iso_week
  - ✅ 杜绝 BI 工具自动派生 vs 源系统物化的口径不一致风险
  - ❌ 切换初期 Leader 看到的"week" 数字会比旧报表略有偏差(跨年周)— 需要在 demo 时主动解释
- **关键词**:ISO 8601 Standardization / Single Source of Truth / Date Semantics Unification

### Decision 12:Dimension 表用 SCD1,SCD2 延期至业务需求出现(YAGNI 原则)
- **日期**:2026-05-18
- **背景**:Kimball 推荐 dim_product 等用 SCD2 跟踪历史变更(比如季节属性变了要留旧值)。但当前 PBI 报表没有任何 "as-of" 历史回溯需求。
- **结论**:切片 1 全部 dim 用 SCD1(覆盖更新),DDL 设计 temporally unbounded 留扩展空间,SCD2 等业务真出现回溯需求时再加。
- **Trade-off**:
  - ✅ 实现简单,ETL 逻辑清晰,符合 YAGNI(You Aren't Gonna Need It)
  - ✅ 不会因为过度设计延误切片 1 交付
  - ❌ 未来如果要加 SCD2,需要重建 dim 表(已在 DDL header changelog 中标记此风险)
- **关键词**:YAGNI Principle / SCD1 / Pragmatic Modeling / Defer Complexity Until Justified

### Decision 13:切片 1 ETL 数据窗口 = 2025-07-01 起,Schema 设计 temporally unbounded
- **日期**:2026-05-18
- **背景**:TW attribution 数据从 2025-07-01 才有(32Degrees 启用 TW 的日期)。是否要把 schema 设计也限制在这个时间窗?
- **结论**:**Schema 是 temporally unbounded(没有时间限制),只是 ETL 的 WHERE 条件先限定 ≥ 2025-07-01**。这样未来如果要纳入 2025-07 之前的 GA4 历史数据,只需要扩 ETL 窗口,不需要改 schema。
- **Trade-off**:
  - ✅ Schema-ETL 解耦,业务窗口变化不影响表结构
  - ✅ 体现"为变化设计"的工程思维
- **关键词**:Schema-ETL Decoupling / Designing for Change / Temporal Boundary Discipline

### Decision 14:Channel meta-category(Non-attributed / Excluded)显式建模,不 drop
- **日期**:2026-05-18
- **背景**:TW 数据里有两个特殊 channel —— `Non-attributed`(其他销售渠道如 Shopify Shop app,非站内流量)和 `Excluded`(exchanges 或 draft orders 等运营订单)。TW pipeline owner 说"不 include 也行"。
- **结论**:**保留并显式标注**(显式建模 > 静默丢弃)。`dim_channel` 表里这两个 meta-category 跟其他 channel 一样有行,前端展示时与 TW UI 一致。
- **Trade-off**:
  - ✅ 显式建模符合"数据完整性优先"原则,不偷偷丢数据
  - ✅ 与 TW UI 一致,方便同事核对口径
  - ❌ Leader 看 PBI 旧报表时这两类是没有的,demo 时需要解释
- **关键词**:Explicit Modeling over Silent Filtering / Data Completeness / Conway's Law in Data Modeling

### Decision 15:Channel 维度展示策略 — channel_source 为默认显示值,channel_group 为上卷层级
- **日期**:2026-05-18(v2 修订 2026-05-21,见 Decision 21)
- **背景**:TW 数据 owner 同事每天看 TW portal,认知锚点是 TW 原始 channel 名(`google-ads` / `facebook-ads`)。高管看 dashboard 需要少数几个大类,不可能看 20+ 根柱子。
- **结论**:`dim_channel` 保留两个字段服务两种粒度 —— `channel_source` 保 TW 原值(前端默认显示值,与 TW portal 1:1 一致),`channel_group` 作为上卷层级供高管级聚合下钻。
- **Trade-off**:
  - ✅ 运营同事在新平台看到的 channel 标签与 TW portal 完全一致,零迁移摩擦
  - ✅ 高管视图有可用的聚合粒度,符合 Kimball 维度上卷设计
  - ❌ Dim 表多一列,但行数低(<25),存储成本可忽略
- **关键词**:Dimensional Roll-up Hierarchy / Stakeholder-Aware Schema Design / Source-Faithful Display
- **⚠️ 注**:此决策最初(v1)将第二列定位为 "legacy GA4 compatibility"。2026-05-21 经 Decision 21 修订为「上卷层级」定位 —— 框架更承重、更经得起面试追问。

### Decision 16:is_paid forward-looking flag 保留,is_web_attributed / is_operational 砍掉
- **日期**:2026-05-18
- **背景**:初稿的 `dim_channel` 设计了 3 个布尔 flag:`is_paid`(付费渠道)/ `is_web_attributed`(站内流量) / `is_operational`(运营订单)。Review 时发现后两个没明确用途。
- **结论**:
  - 保留 `is_paid`:切片 4+ 要做 ROAS 指标(`SUM(revenue) / SUM(ad_spend) WHERE is_paid = TRUE`),提前埋好可避免后续 ALTER TABLE
  - 砍 `is_web_attributed` / `is_operational`:没明确指标用途,后续真需要再加
- **Trade-off**:
  - ✅ Forward-looking design 让切片 4+ 实现 ROAS 时变成一行 SQL
  - ✅ 避免过度设计,只保留有明确用途的 flag
- **关键词**:Forward-Looking Dimension Flags / Pre-encoded Business Taxonomy / One-Line Metric Implementation

### Decision 17:`fact_orders_line` 时区采用 DST-aware `from_utc_timestamp('America/New_York')`
- **日期**:2026-05-19
- **背景**:Panoply legacy 一直用固定的 `processed_at - 5h`(EST,UTC-5)做时区转换。但 32 Degrees 在纽约,实际时区是 `America/New_York` — 冬季 EST(UTC-5)、夏季 EDT(UTC-4),每年两次 DST 切换。Legacy 在 EDT 期间有 ~1% 系统性偏差(夏季跨午夜订单被误归到前一天)。
- **结论**:新平台采用 Spark 内置 `from_utc_timestamp(processed_at, 'America/New_York')`,自动处理 DST。
- **Trade-off**:
  - ✅ 严格正确,跟纽约本地用户认知一致
  - ✅ **修正 legacy 系统的工程缺陷**,作为新平台的质量提升点
  - ✅ 简历讲故事素材:"identified and corrected legacy timezone bug"
  - ⚠️ Day 5 reconciliation 时夏令时切换日附近(2025-11-02 / 2026-03-09 附近 UTC 晚间小时)跟 legacy 会有 < 1% 微差异 — 已在 design doc §8.7 文档化为"intentional correction"
- **关键词**:DST-aware Timezone / Legacy Bug Correction / Engineering Quality Improvement

### Decision 18:DQ 框架采用 Multi-tier SLO(PASS / WARN / FAIL),阈值基于实际 baseline 校准
- **日期**:2026-05-19
- **背景**:DQ 初稿用单层阈值(0.1% channel unmatched 报 warning)。Review 时发现这个阈值比实际健康基线还严格 — TW ↔ Shopify 实际 match rate 99.85%,即 baseline unmatched = 0.15%,0.1% 阈值会 100% 触发告警,造成告警疲劳。
- **结论**:采用 SRE-style 多层 SLO 设计:
  - **PASS**(默默通过):channel < 0.5% / product < 1%
  - **WARN**(告警,pipeline 继续):channel 0.5%-2% / product 1%-5%
  - **FAIL**(中止 pipeline):channel ≥ 2% / product ≥ 5%
  - 阈值基于实际 baseline(0.15%)校准:WARN ~3x baseline 缓冲,FAIL ~14x baseline
- **Trade-off**:
  - ✅ 避免告警疲劳(WARN 阈值给正常波动留 3x 缓冲)
  - ✅ 区分"操作信号"(WARN,记录到 DQ 报告)vs "数据完整性破坏"(FAIL,立即停)
  - ✅ 阈值有数据支撑,不是拍脑袋
  - ✅ 简历金句:"Multi-tier DQ SLO calibrated against empirical healthy baseline"
- **关键词**:Multi-tier SLO / Empirical Calibration / Alert Fatigue Mitigation / SRE-style Observability

### Decision 19:ERS 上游 schema 演进 — 采用双格式 schema-detection 自动识别
- **日期**:2026-05-19
- **背景**:ERS 月度上传 CSV,2026 年改了格式:`Unique_Identifier` → `SKU`,`Vend_ID` → `Style#`,`Item_Description` → `Item Description`(带空格),并新增 Geodis 物流 / Ladder 预测等列。如果只支持新格式,以后想重跑历史月份就要先手动转换。
- **结论**:ETL 自动检测 ERS schema 版本(legacy / current),内部规范化到统一字段名(`sku`, `vend_id`, `item_description`, `season`, `group_name`, `gender`, `class_name`)。
- **Trade-off**:
  - ✅ 历史月份的旧格式 CSV 可以无修改直接重跑
  - ✅ schema evolution tolerance — 跟之前 Panoply 老 tags / 新 metafield 双路径并行是**同一套工程思维**的延续
  - ✅ 简历金句:"Built schema-evolution-tolerant ingest detecting and normalizing two distinct source schema versions"
  - ❌ 代码复杂度略增(增加 detect_and_normalize_ers 函数),但收益明显大于成本
- **关键词**:Schema Evolution Tolerance / Ingest Robustness / Backward Compatibility

### Decision 20:ERS 原始文件落地用共享 Volume,不建项目专属 Volume
- **日期**:2026-05-20
- **背景**:dim_product 需要读 ERS CSV。新 schema `analytics_platform_32degrees` 下没有 Volume,需等同事创建。
- **结论**:ERS CSV 上传到共享的 `mvdevdatabricks.32degrees.raw_uploads/ers/` 子目录,不为本项目单独建 Volume。
- **Trade-off**:
  - ✅ ERS 是全公司共享的产品主数据,放共享 raw landing zone 由各项目 ETL 各自消费,是正确的 conformed reference data 架构
  - ✅ 不阻塞,不依赖同事
  - ✅ 命名空间清晰度不受影响 — 项目自己产出的 dim/fact 表全部仍在独立 schema 内,Volume 只是原始文件落地区
  - ✅ 简历金句:"Treated ERS product master as a shared conformed reference source in a common raw zone, consumed independently by the dim_product ETL"
- **关键词**:Shared Raw Zone / Conformed Reference Data / Cross-project Data Reuse

### Decision 21:channel 第二列从「GA4 兼容」重定位为「Kimball 上卷层级」,并改名 channel_group
- **日期**:2026-05-21
- **背景**:重建 dim_channel 种子时 review 了 Decision 15 的 dual-display 设计。原方案把第二列 `legacy_channel_group` 定位为「服务高管对 GA4 旧报表的认知惯性」。问题:GA4 本身正在被 TW 取代,一个「为已退役系统做兼容」的字段经不起面试追问("GA4 都不用了,这列谁在看?")。
- **结论**:
  - 列改名 `legacy_channel_group` → `channel_group`
  - 重新定位:它不是「GA4 兼容字段」,而是 channel 维度的**上卷层级**(roll-up hierarchy)——`channel_source`(24 个明细) → `channel_group`(~10 个大类)。这是 Kimball 维度建模的标准 drill-down hierarchy,等同于 product → category、date → month → year。
  - 分组值(Paid Search / Paid Social / Email)是全行业通用的功能分类,并非 GA4 专有 —— 用它当上卷层级,与 GA4 是否退役无关。
- **Trade-off**:
  - ✅ 框架是「承重的」—— 上卷层级撑起高管聚合视图,而非可有可无的兼容列
  - ✅ 经得起面试 3 层追问(Kimball 教科书概念 vs 「leader 的旧习惯」这种弱解释)
  - ✅ 与 dim_date / dim_product 的层级设计语言统一
  - ❌ 需同步改 DDL 列名 + notebook 02 + 重建表 —— 但 dim_channel 本就要重建(种子值错误),边际成本为零
- **关键词**:Dimensional Roll-up Hierarchy / Drill-down Path Design / Schema Semantics Refactoring
- **取代**:本决策取代 Decision 15 v1 对第二列的定位。

### Decision 22:订单类型业务规则物化为 `is_sales_attributable` flag
- **日期**:2026-05-22
- **背景**:Day 5 reconciliation 发现新平台比 Panoply 系统性高 ~3%。根因是 Panoply 的 channel 销售 report 在源头用 4 道 WHERE 过滤排除了换货 / 退款 / exchange(`%EXC%`)/ Returnly-tag 退货订单。Leader 明确:channel 销售分析不应含 refund/replacement(replacement 会重复计数,return 会虚低)。
- **结论**:不在每个查询里散落复刻这 4 道过滤(Panoply 老做法,易写漏、口径不一致),而是在 `fact_orders_line` 物化一个 `is_sales_attributable` 布尔列,把"这一行算不算 channel-attributable 销售"这个业务语义集中编码一次。reconciliation / metrics API / 未来的 refunds report 统一消费同一个 flag。原始全量数据保留,只打标不删除。
- **Trade-off**:
  - ✅ Single source of truth — 业务规则一处定义,杜绝 Panoply 那种"某个 report 忘加 Returnly 过滤"的口径漂移
  - ✅ 原始数据不丢,毛/净销量两种口径都可算;退货 report 直接用 `is_sales_attributable = FALSE`
  - ✅ 简历素材:business rule 下沉数据层 / 多源业务规则统一建模
  - ❌ 第一版无法 100% 复刻:换货表(Replacements_news)、退款表(refund1_news)、Shopify `tags`(Returnly)均未接入 Databricks,需先补 ingestion
  - ⚠️ 当前 reconciliation 用查询级近似(`%EXC%` + `is_refunded`)替代,残差 ~2% 已文档化归因
- **关键词**:Business Rule Materialization / Single Source of Truth / Semantic Layer / BI Logic Decoupling
- **状态**:已决策,待落地(列入 Slice 1 收尾 / Slice 3 backlog)

### Decision 22 v2 修订(2026-05-26)
- **措辞更正**:原文"换货表(Replacements_news)"有误 —— Replacements_news
  是**补发(replacement)表**,EXC 才是换货单,二者是独立的两类。
- **三类排除信号最终敲定**:
  - EXC:`order.name LIKE '%EXC%'`(Shopify 原生)
  - refund:Shopify 原生 `refund` 父表(system source-of-record,
    取代 Panoply 的 tag 反推 —— 原生表抓到了 tag 法漏掉的未打标退款)
  - replacement:Shopify order metafield(`replace_refund` 等三列)
- **Returnly 停用**:原 trade-off 中"接入 Shopify tags 处理 Returnly"作废。
- **落地策略调整为增量式**:EXC + refund 先落地(信号已就绪),
  replacement 待 Fivetran 同步 order metafield 后补。notebook 04 预留接口,
  缺失信号优雅降级 —— 体现 fault-tolerant pipeline design。
- **关键词**(新增):Native Object over Tag-Reverse-Engineering /
  System Source-of-Record / Incremental Signal Integration / Fault-tolerant ETL

### Decision 22 v3 修订(2026-05-27)— 最终模型,取代前述所有版本
- **触发**:读 Panoply 源码 + week-28 逐项对账证实"整单排除 refund"是错的
  (残差 1.97%→6.57%)。
- **最终模型**:
  - `is_sales_attributable = NOT(is_exc_order OR is_replacement_order)` —— 仅整单
    排除 EXC + replacement 两类
  - refund 改为**行级净扣**:`refunded_quantity` 列 = SUM(order_line_refund.quantity)
    覆盖全 restock_type(含 cancel);净销量 = quantity − refunded_quantity
  - `is_refunded` / `is_refund_order` 废弃删除
  - replacement 信号 = Shopify `order_metafield` 表(独立表),notebook 04 表存在性
    自动检测 + 优雅降级
- **对账结果**:week 28 overall −1.51%,残差 100% 归因(EXC 2,209 + refund 6,573 +
  cancel 803),通过 trust gate。
- **关键词**:Reconciliation-Driven Model Correction / Restock-type-aware Line-level
  Refund Netting / Fully-itemized Residual Attribution

  ### Decision 23:Amazon 入库数据作为平台独立 domain,放主 schema 用前缀隔离
- **日期**:2026-05-28
- **背景**:Leader 要求把 Panoply 上的 Amazon FBA 入库数据(shipment items +
  shipments 两个 connector)迁到新平台,每周一更新给 planning 同事。Amazon 数据
  与 Shopify/TW 无任何业务 join key。放哪里?独立 schema 还是主 schema?
- **结论**:放主 schema `analytics_platform_32degrees`,用 `amazon_` 表名前缀隔离。
  不新建独立 schema(无 catalog 级 CREATE SCHEMA 权限,且无必要)。
- **Trade-off**:
  - ✅ Amazon 成为平台的一部分,强化"multi-domain 数据平台"叙事
  - ✅ 与 Slice 1 Kimball 域共享指标服务层 / 前端门户 / DQ 框架 / 调度
  - ✅ 命名前缀清晰隔离两个无 join key 的 domain —— 不强行塞进同一星型模型
  - ❌ 同一 schema 下两种建模范式(Kimball star vs Medallion)并存,靠命名约定区分
- **关键词**:Multi-domain Platform / Prefix-isolated Namespace / Domain Isolation without Schema Proliferation

### Decision 24:Amazon 域用 Medallion(Bronze/Silver/Gold),不用 Kimball
- **日期**:2026-05-28
- **背景**:Slice 1 用 Kimball 星型。Amazon 域是否也套星型?
- **结论**:用 Medallion 分层。Bronze 存 API 原始 JSON(schema-on-read,容忍
  Amazon 字段新增);Silver 规范化 typed schema(schema-on-write + DQ gate);
  Gold 做 items⨝shipments 的 receiving summary(复刻 Panoply query model 的 join)。
- **Trade-off**:
  - ✅ Medallion 适合"原始 API → 清洗 → 业务视图"的 ingestion 场景,比强套
    fact/dim 更自然
  - ✅ 同时展示两种主流建模范式(Kimball + Medallion),简历技术广度
  - ✅ Bronze 原始留痕 + 90 天 retention 支持 replay
  - ❌ 团队需理解两套范式;用 README/doc 说明何时用哪种
- **关键词**:Medallion Architecture / Schema-on-Read Bronze / Schema-on-Write Silver / Replay Window

### Decision 25:Amazon 双源 completeness 修正(referential + SKU-level)
- **日期**:2026-05-29
- **背景**:gold(items ⨝ shipments,复刻 Panoply `amazon_ship` inner join)行数持续 < items,
  且单个 shipment 的 SKU 数也少于 Panoply。两层 completeness 缺陷,同一根因家族:
  两个 SP-API feed 各自用 8 天 LastUpdated 窗口,但收货分批陆续到 ——
  - 缺陷①(referential):shipment 状态早已不变落窗口外,但其 item 收货量仍在更新落窗口内
    → 67 个 item 行的 shipment 维度缺失,inner join 静默丢弃。
  - 缺陷②(SKU-level):同一 active shipment 内,最后更新早于 8 天的 SKU 行被 items 窗口漏掉
    (FBA19CRBL6RZ:窗口只返回 12/20 SKU)。
- **修正**:
  - 02 shipments → key-driven:从 silver_item 读 distinct shipment_id,用 ShipmentIdList 按 ID 拉。
  - 01 items → 两段式:Stage 1 用 DATE_RANGE 仅发现活跃 shipment_id(丢弃其 item 行);
    Stage 2 对每个活跃 shipment 用 GET /shipments/{id}/items(无日期、单页不翻页)拉全量 SKU。
  - DAG 01∥02→03 改为 01→02→03。
- **SP-API 实战坑**:/shipmentItems 的 QueryType 只认 DATE_RANGE/NEXT_TOKEN,无 SHIPMENT;
  取单 shipment 全量 item 走 path 形态 /shipments/{id}/items;该 path endpoint 不能用 NextToken
  翻页(会重复吐行触发 429);限流用 Retry-After + 指数退避 + jitter + 节流。
- **验证**:items_without_shipment 67→0;FBA19CRBL6RZ 12→20 SKU;gold 191→258→826(=item 全量数)。
  新平台 received 为到仓终值,Panoply 同 shipment received 全为 0(5/18 冻结的在途快照)→
  新平台更全 + 更新,"修正 legacy 过期快照"实证。
- **关键词**:Referential Completeness · SKU-level Completeness · Two-stage Discover-then-Hydrate ·
  Fact-key-driven Dimension Fetch · Cross-feed Window Skew · SP-API Throttling/Backoff · Legacy Snapshot Correction

### Decision 26:Amazon 范围裁剪 —— 只保留活跃 shipment,不做历史回填
- **日期**:2026-05-29
- **背景**:量化历史深度发现新平台 gold 覆盖 21 个 shipment(2024-07~2026-05,近期活跃),
  Panoply 累积 1363 个(2022-10 起全史)。表面看新平台缺 98.5% 历史。
- **业务用途核实**:planning 同事用此数据跟进近期活跃 shipment 以制定补货/入库计划,
  不需要历史已定讫 shipment 的记录(过去几年的死数据对前瞻性 planning 无价值)。
- **决策**:不做历史回填。新平台的"发现窗口 → 只抓近期活跃 shipment"恰好匹配 planning 的活跃视图
  需求,是特性而非缺陷。明确拒绝从 Panoply 搬全史(路线 A)—— 会污染活跃视图、增加维护负担、
  灌入对用例无价值的死数据。
- **Trade-off**:✅ 数据范围精确匹配业务用途;活跃视图干净;零额外维护;不依赖 Panoply 长期存活。
  ❌ 不能用于历史回溯分析 —— 但不在用例内;若将来需要可另起一次性 backfill(已评估路线 A/B)。
- **历史深度差异归因**:新平台 21 vs Panoply 1363,系有意范围裁剪,非数据丢失。
- **关键词**:Scope-driven Data Modeling · Business-aligned Retention · Active-window Design

### Decision 27:slice_1 定时作业算力选型 —— Personal Compute,非 job cluster / serverless
- **日期**:2026-06-01
- **背景**:Phase 4 给 slice_1 上线每日调度时,首选 ephemeral autoscaling job cluster(成本最优、生产标准)。但 `databricks jobs` 重建后 Run 报 `PERMISSION_DENIED: not authorized to create clusters` —— workspace 禁用了「创建 cluster」权限(与此前 PAT 被禁属同一类组织管控)。
- **决策**:定时作业改用已有权限的 Personal Compute(`existing_cluster_id`),已验证全绿上线。serverless 亦排除 —— notebook 04 用 `.cache()` 物化 ~10M 行 join,serverless 不支持 `.cache()`。
- **Trade-off**:✅ 零等待、零审批,沿用已证明能跑的算力,管线立即上线;Personal Compute 跑完自动 terminate,闲时成本有界。 ❌ 失去「ephemeral job cluster」这一算力关键词;定时作业跑在 all-purpose cluster 上属轻度反模式。算力/成本优化叙事移至 Phase 6(Azure Container Apps 闲时缩到零)。
- **复查条件**:若日后 workspace 放开 cluster 创建权限,或 notebook 04 重构去掉 `.cache()`,可切 job cluster 或 serverless 统一算力(job-cluster 配置已存于 git 历史)。
- **关键词**:Platform Governance Constraint · Compute Selection Trade-off · Serverless `.cache()` Limitation · Pragmatic Delivery

### Decision 28:fact_orders_line 增量加载 —— updated_at watermark + Delta MERGE
- **日期**:2026-06-0X
- **背景**:notebook 04 原为全量重写(每次重算 2025-07-01 至今),随数据增长跑时线性变长,且是初级做法。
- **决策**:改为增量。水位线用 Shopify `order.updated_at`(退款/改单会 bump,故晚到退款能被重新捕获);每次从"水位线 − 2 天"读取(lookback 兜底同步延迟/晚到数据);用 **Delta MERGE**(key=`shopify_line_id`)做 upsert,而非分区覆盖——因为退款会回填老周(iso_week)数据,分区覆盖会漏。保留 `FULL_REFRESH` 开关做 backfill/recovery。
- **Trade-off**:✅ 增量跑时从全量 18 min 降到数十秒;MERGE 天然处理退款回填;单一管线 + flag 切全量/增量是生产标准。 ❌ fact 新增一列 `order_updated_at`(水位线来源,亦为有用 lineage);MERGE 比 overwrite 略复杂。
- **验证**:全量建基线后切增量,对账 row_count==distinct_lines(无重复)、total_qty/refunded 一致。
- **关键词**:Incremental Pipeline · Delta MERGE Upsert · Watermark + Lookback · Late-arriving Data · Backfill Switch · Idempotent Load

## Decision 29 — ACA scaling: backend min=1, frontend min=0
Internal-ingress backend behind a synchronous frontend proxy + scale-to-zero =
first request after idle eats full cold-start and fails (this was the root cause
of the "non-JSON response" bug). Keep the backend warm (min=1); frontend still
scales to zero. Explicit latency-vs-idle-cost trade-off.

## Decision 30 — Three-mode Databricks auth behind DATABRICKS_AUTH_TYPE
PAT / OAuth U2M / OAuth M2M selectable by one env var. M2M (service-principal
client-credentials via credentials_provider + oauth_service_principal) for the
headless container — U2M's browser flow can't run unattended; PAT is disabled
org-wide. Requires databricks-sdk. U2M kept for local dev.

## Decision 31 — Staged mock→live deployment
Deploy the backend in mock mode first to validate the full cloud path
(ingress / proxy / KV secrets / managed identity) decoupled from Databricks
credentials; flip METRICS_DATA_SOURCE=databricks once the SP is ready. Reuses
the dual-mode client.

## Decision 32 — dpsync metafield: tap, don't migrate (yet)
Use dpsync.shopify_32degrees.order_metafield for the replacement signal only
(wide format: replace_refund=='Replace'), WITHOUT migrating the rest of the
pipeline off Fivetran. Incremental adoption pending validation (historical
backfill from 2025-07-01, schema stability, freshness SLA). notebook 04 §3b
adapted from the assumed Fivetran EAV shape to the dpsync wide shape.
---

## 6. 项目仓库

- **GitHub**:https://github.com/sichensong-99/analytics-platform
- **Public**:Yes(简历可附链接)
analytics-platform/
├── frontend/                  # Next.js portal (Phase 1 ✅)
├── metrics-service/           # FastAPI metrics service (Phase 2A ✅)
├── databricks-notebooks/      # Data warehouse modeling (Phase 3)
├── docs/                      # Documentation
│   ├── data_contracts/        # Data contracts
│   ├── data_modeling/         # ER diagrams, dimensional model
│   ├── architecture.md
│   └── streaming_module_plan.md
├── NORTH_STAR.md              # ⭐ 最高决策原则
├── PROJECT_CONTEXT.md         # 项目背景与决策
├── ROADMAP.md                 # 阶段计划
├── PROGRESS.md                # 当前进度
├── SIA_PROFILE.md             # 个人偏好
└── README.md

---

## 7. 简历定位与求职目标

- **目标档位**:中级 / 中级偏高 Data Engineer(国内一线 35-50K,冲刺 50-60K)
- **面向公司**:国内中大厂、外企在中国分部、成熟创业公司
- **回国时间**:待定(根据春招/秋招节奏)
- **简历核心叙事**:
  > "主导设计并落地端到端数据平台,从多源数据接入到 Lakehouse 数仓建模、指标服务化、自助分析门户,配套调度、数据质量、流处理等平台能力,替代 Power BI Service 节省 $X/年。"

---

## 8. Remaining Tasks Tracker(2026-05-19 起,已归档)

> ⚠️ **本节已过时**(停留在 Slice 1 启动前,Day 2-5 当时还没做)。
> 当前真实进度与待办**一律以 PROGRESS.md 顶部 CURRENT STATE 为准**。
> 本节仅保留作历史,不要据此判断进度。

### P0 任务(Day 2-5 之前必做)

- [ ] **Task E**:YAML 指标定义 `quantity_by_style_channel_week.yaml` (~1h)
- [ ] **Task F**:Next.js mock UI for `Style-channel (quantity)` page (~3-4h)
- [ ] **Task G**:DQ YAML 配置(用 Track 3 框架,4 张表)(~1h)

### H 加分项(独立,完成 P0 后做)

- [ ] **H2**:Reconciliation methodology 脚本 + Excel 模板 (~2h)
- [ ] **H3**:补 `existing_data_inventory.md` §5.2-5.N PBI 页映射 (~4-6h,分多次)
- [x] **H5**:Decision Log 17/18/19 ✅ 2026-05-19
- [ ] **H6**:Demo script(Task F 完成后做)(~1.5h)

### 阻塞中(等同事开 `mvdevdatabricks.analytics_platform_32degrees` schema)

- [ ] **Day 2**:Dim ETL — 跑 notebook 01/02/03(~半天)
- [ ] **Day 3**:Fact ETL — 跑 notebook 04(~1 天)
- [ ] **Day 4**:FastAPI 真连 Databricks SQL Warehouse(~半天)
- [ ] **Day 5**:Next.js wire-up + DQ + Reconciliation + Leader Demo(~1 天)

### 后期 Phase(已锁定的项目路线图)

- [ ] Slice 2: revenue page(复用 Slice 1 基础)
- [ ] Slice 3: refunds page
- [ ] Slice 4: ROAS page(加 fact_attribution_touchpoint)
- [ ] Phase 4: Workflows 调度 + DQ 落地
- [ ] **Phase 4.5 ⭐**: Streaming 实时模块(简历核心)
- [ ] Phase 5: Redis + Metrics Catalog + Lineage
- [ ] Phase 6: 部署 + 文档 + 成本核算