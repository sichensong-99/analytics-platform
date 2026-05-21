# Internal Analytics Platform — Roadmap

> Last updated: 2026-04-28
> Current phase: **Phase 2A 完成,等数据期间(Track 1/2/3 并行)**

---

## 🗺 整体 Schedule 流程图

现在 ──┐
│
├─ 等 Databricks 数据期间(并行 3 件事)
│   ├── Track 1:PBI 数据源盘点
│   ├── Track 2:目标 schema 设计文档
│   └── Track 3:数据质量框架代码骨架
│
▼
Phase 2B/3:Databricks 数仓建模(数据来后)
│
▼
Phase 2C:对接真实数据
│
▼
Phase 4:调度 + 数据质量框架落地
│
▼
Phase 4.5:⭐ 实时模块(渠道异常监控)
│
▼
Phase 5:Redis + Catalog + Lineage
│
▼
Phase 6:上线 + 文档 + 成本核算
│
▼
✅ 项目完成 → 投简历 → 准备面试
---

## Phase Overview
Phase 1 ✅ → Phase 2A ✅ → 等数据(Track 1/2/3) ⏳ → Phase 2B/3 →
Phase 2C → Phase 4 → Phase 4.5 (实时) → Phase 5 → Phase 6
**总周期**:11-15 周(约 3-4 个月)

---

## Phase 1:Portal MVP ✅

**Status**: ✅ Completed

- [x] Next.js + TypeScript + Tailwind 项目骨架
- [x] JWT-based 登录(httpOnly cookie)
- [x] Dashboard 列表页 + 详情页
- [x] ECharts 图表(line, bar)
- [x] CSV 导出
- [x] Mock 数据按 Data Contract schema 设计
- [x] Data Contract 文档(Shopify, Triple Whale)

**简历素材**:全栈交付能力 + Data Contract 工程实践

---

## Phase 2A:Metrics Service Skeleton ✅

**Status**: ✅ Completed

- [x] FastAPI 项目结构 + uv 依赖管理
- [x] YAML 指标定义(4 个指标:revenue/aov/roas/ad_spend)
- [x] 指标 versioning + changelog
- [x] YAML loader + 缓存
- [x] JWT 鉴权(共享 secret with Next.js)
- [x] Mock Databricks client(可替换接口)
- [x] CORS 配置
- [x] FastAPI 自动 docs(/docs)
- [x] Next.js 改造为通过 FastAPI 取数

**简历素材**:数据服务化 + 指标平台 + Versioned Metrics

---

## ⏳ 等数据期间(并行 Track)

**目标**:Databricks 数据进来前,把所有"前置准备"都做好。

### Track 1:PBI 数据源盘点(1-2 天)
- [ ] 打开 PBI report,查看 Power Query 数据源
- [ ] 记录已有的 catalog.schema.table 名字
- [ ] 验证查询权限
- [ ] 写 `docs/existing_data_inventory.md`

### Track 2:目标 Schema 设计(2-3 天)
- [ ] 反推 PBI dashboard 需要的 fact + dim 表
- [ ] mermaid 画星型模型 ER 图
- [ ] SCD 类型决定(Type 1 / Type 2)
- [ ] 写 `docs/data_modeling/sales_star_schema.md`

### Track 3:数据质量框架骨架(2-3 天)
- [ ] YAML 驱动的 DQ 框架代码
- [ ] 检查类型:not_null / unique / range / freshness
- [ ] 写在 `metrics-service/data_quality/`
- [ ] Phase 4 落地时直接用

---

## Phase 2B/3:Databricks 数仓建模 ⏳

**Status**: 等数据,数据来后启动
**预计**:3-4 周

- [ ] ODS 层:`ods.shopify_orders_raw`, `ods.triplewhale_attribution_raw`
- [ ] DWD 层(维度建模):
  - [ ] `dwd.fact_orders`
  - [ ] `dwd.fact_attribution`
  - [ ] `dwd.dim_customer`
  - [ ] `dwd.dim_product`
  - [ ] `dwd.dim_date`
  - [ ] `dwd.dim_channel`
  - [ ] `dwd.dim_style`
- [ ] DWS 层:`dws.daily_revenue`, `dws.channel_performance` 等
- [ ] PySpark notebooks 5 个:
  - [ ] `01_ods_to_dwd_orders`
  - [ ] `02_ods_to_dwd_attribution`
  - [ ] `03_build_dimensions`
  - [ ] `04_dwd_to_dws_revenue`
  - [ ] `05_dwd_to_dws_channel`
- [ ] Shopify + Triple Whale 跨源整合(`dwd.fact_orders_with_attribution`)

**简历素材**:数仓分层 + Kimball 维度建模 + PySpark ETL + 多源整合

---

## Phase 2C:对接真实数据 ⏳

**预计**:1 周

- [ ] YAML 指标 SQL 改写为查 DWS 真表
- [ ] `databricks_client.py` 替换 mock 为真实 SQL connector
- [ ] 端到端测试:Next.js → FastAPI → Databricks → 真数据

**简历素材**:全链路打通

---

## Phase 4:调度 + 数据质量 ⏳

**预计**:1 周

- [ ] Databricks Workflows DAG(ODS → DWD → DWS)
- [ ] 失败重试 + 告警(Slack / Email)
- [ ] 数据质量框架接入(YAML 驱动)
- [ ] DQ 校验作为 pipeline 的一个 task
- [ ] 文档:架构图、调度策略

**简历素材**:数据治理 + Orchestration

---

## 🆕 Phase 4.5:实时模块 ⏳

**预计**:5-7 天
**详细计划**:见 `docs/streaming_module_plan.md`

**业务**:实时渠道异常监控(ROAS drop)
**技术**:Databricks Auto Loader + Structured Streaming + Delta Lake

### P0(3 天)
- [ ] 模拟数据生成器(orders + ads)
- [ ] Auto Loader streaming notebook
- [ ] 5-min sliding window
- [ ] Channel-level metrics
- [ ] Simple anomaly rule

### P1(再 2-3 天)⭐ 别漏
- [ ] Stream-stream join
- [ ] Checkpoint + Exactly-once
- [ ] Watermark + 乱序处理
- [ ] dropDuplicatesWithinWatermark
- [ ] 流批一体(Delta Lake unified)

**简历素材**:Streaming + 流批一体 + Exactly-once

---

## Phase 5:平台化升级 ⏳

**预计**:1-2 周

- [ ] Redis 缓存层
- [ ] Metrics Catalog 页面(展示所有指标 + 版本 + 血缘)
- [ ] 指标血缘可视化(ECharts graph 组件)
- [ ] 缓存效果量化(查询时间对比)

**简历素材**:平台化 + 性能优化 + 血缘追踪

---

## Phase 6:上线 + 收尾 ⏳

**预计**:1 周

- [ ] 部署(Vercel 前端 / 公司服务器后端)
- [ ] 完整文档(架构图、API 文档、用户指南)
- [ ] 成本核算报告(PBI 节省 + 缓存优化)
- [ ] 使用统计(用户数、查询量、热门指标)
- [ ] 写一篇技术博客
- [ ] GitHub README 美化(架构图、截图、demo 视频)

**简历素材**:量化成果 + 项目运营

---

## 简历最终版(Phase 6 后)

> **企业内部数据分析平台 / 主导设计与开发** | 2026.04 - 2026.07
> 
> 替代 Power BI Service,降低团队订阅成本 $X/年,服务 N 名团队成员
> 
> **数据架构**
> - 在 Databricks Lakehouse 上设计三层数仓(ODS / DWD / DWS),整合 Shopify、Triple Whale 多源异构数据
> - 基于 Kimball 方法论实现维度建模,产出 fact_orders、dim_product、dim_customer 等核心事实/维度表
> - 使用 PySpark 实现 ETL pipeline,支持全量与增量更新
> - 在数据接入前定义跨团队 Data Contract,明确 schema、粒度、质量预期与 SLA
> 
> **数据服务层**
> - 设计并实现统一指标服务(Metrics Service),解耦指标定义与消费逻辑
> - 基于 YAML 配置驱动的指标 DSL,实现指标口径统一管理,新增指标 0 代码改动
> - 设计指标版本管理机制(versioned metrics),支持口径变更追踪与 breaking change 标记
> - FastAPI 提供 RESTful 接口,引入 Redis 缓存,降低 Databricks 查询成本 70%
> 
> **数据治理**
> - 实现指标血缘追踪与可视化,提供影响分析能力
> - 构建 YAML 驱动的数据质量校验框架(完整性、唯一性、新鲜度等维度)
> - 使用 Databricks Workflows 编排 pipeline,实现任务依赖、失败重试、告警通知
> 
> **流处理**
> - 基于 Databricks Structured Streaming + Auto Loader 实现实时渠道异常监控
> - 实现 stream-stream join、watermark 乱序处理、exactly-once 语义
> - Delta Lake 流批一体存储,统一实时与离线分析
> 
> **前端展示**
> - Next.js + ECharts 实现自助分析门户,支持 dashboard 浏览、指标目录、CSV 导出
> 
> **技术栈**:Databricks · PySpark · Spark Structured Streaming · Delta Lake · FastAPI · Next.js · Redis · ECharts · YAML