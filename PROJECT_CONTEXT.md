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
| Shopify 订单数据 | 等数据同事导入 Databricks(进行中) |
| Triple Whale 广告归因数据 | 等数据同事导入 Databricks(进行中) |
| 已有的 Databricks 数据 | 部分已有(支撑现有 PBI report) |

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

### Decision 15:Channel 双显示策略 — channel_source(TW 原值) + legacy_channel_group(GA4 风格)
- **日期**:2026-05-18
- **背景**:TW 数据 owner 同事每天看 TW UI(用 `google-ads` / `meta` 这种平台名);Leader 看了多年的 PBI 报表(用 `Paid Search` / `Paid Social` 这种功能名)。两类用户的认知习惯不同。
- **结论**:`dim_channel` 表里同时保留两个字段 —— `channel_source` 保 TW 原值(服务 TW 同事),`legacy_channel_group` 加 GA4 风格分组(服务 Leader 对旧 PBI 的认知惯性)。同一 dim 表服务两类用户,**Conway's Law 在数据建模中的应用**。
- **Trade-off**:
  - ✅ 不强迫任何一方学对方的术语
  - ✅ 切换 PBI → 新平台时降低认知摩擦
  - ❌ Dim 表多一列,但行数低(<20),存储成本可忽略
- **关键词**:Dual-Display Dimension / Stakeholder-Aware Schema Design / Conway's Law / Platform Migration Cognitive Cost Mitigation

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
---

## 6. 项目仓库

- **GitHub**:https://github.com/sichensong-99/analytics-platform
- **Public**:Yes(简历可附链接)
analytics-platform/
├── frontend/                  # Next.js portal (Phase 1 ✅)
├── metrics-service/           # FastAPI metrics service (Phase 2A ✅)
├── databricks-notebooks/      # Data warehouse modeling (Phase 3, TODO)
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

## 8. Remaining Tasks Tracker(2026-05-19 起)

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