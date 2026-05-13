# Project Progress

> Last updated: 2026-05-05
> 每次 chat 结束前,Claude 帮助更新这份文档,然后重新上传到 Project Knowledge

---

## ✅ 已完成

### Phase 1:Portal MVP(2026-04 完成)
- Next.js portal 跑通(登录 + 列表页 + 2 个详情页)
- Mock 数据按 Data Contract 设计
- Data Contracts 写好(Shopify, Triple Whale)
- 部署到 GitHub:https://github.com/sichensong-99/analytics-platform

### Phase 2A:Metrics Service(2026-04 完成)
- FastAPI 框架 + uv 依赖
- 4 个指标(YAML + version + changelog)
- JWT 鉴权 + CORS
- Mock Databricks client(抽象接口)
- Next.js 改造完成,通过 FastAPI 取数
- API docs:http://localhost:8000/docs

### Project Brain 搭建(2026-04 完成)
- NORTH_STAR.md 最高决策原则
- PROJECT_CONTEXT.md 项目宪法
- ROADMAP.md 完整阶段计划
- PROGRESS.md 进度跟踪
- SIA_PROFILE.md 个人偏好
- streaming_module_plan.md 实时模块计划
- Project Instructions 配置完成

### Track 1 — 数据资产探索(2026-05-05 完成)
- ✅ 摸清 Databricks 上所有表的结构和粒度
  - Shopify @ `mvdevdatabricks.shopify_32degrees`:8 张表
    (order, order_line, order_line_refund, return, return_line_item,
     return_shipping_fee, customer, customer_tag)
  - TW @ `mvdev_federated_catalog.triple_whale`:5 张表
    (attribution_order, attribution_order_click,
     attribution_order_journey_event, summary_page_metric,
     summary_page_metric_chart_point)
- ✅ 数据接入工具确认:Shopify 走 Fivetran(managed ELT),TW 走 custom pipeline
- ⚠️ 发现并验证 2 个上游数据问题(详见下方"当前卡点")

### Track 3:DQ 框架代码骨架(2026-05-13 完成)
- ✅ 基于抽象基类的可扩展架构(BaseChecker)
- ✅ 4 种 checker:not_null / unique / range / freshness
- ✅ YAML 配置驱动(2 个示例:shopify_orders, tw_attribution)
- ✅ Runner + Reporter(console + JSON 双格式输出)
- ✅ 15 个测试场景全部通过(单元测试 + 端到端测试)
- ✅ 完整 README + commit history
- 位置:`metrics-service/data_quality/`
---

## ⏳ 当前阶段:等数据期间(Track 1/2/3 并行)

**等数据状态**:已发邮件给数据同事,等回复(预计 1-2 个工作日)

**正在做的事**:
- [x] Track 1:数据资产探索(完成探索,待写文档)
- [ ] Track 1:写 `docs/existing_data_inventory.md` 文档化
- [x] ~~Track 3:DQ 框架代码骨架~~ ✅ 完成
- [ ] Track 2:星型模型框架级设计(下一个)

---

## 🚧 当前卡点(2026-05-05 发现)

### 卡点 1:Fivetran Shopify connector 配置错误
**现象**:Schema 名 `mvdevdatabricks.shopify_32degrees` 但实际装的是 Appaman 的店数据。
**证据**:
- 113K 订单中 100% `order_status_url` 指向 appaman.com,0 命中 32degrees.com
- 99% `order_line.vendor` = "Appaman"
- 跨源 join Shopify ↔ TW(7 天同窗口),1885 单 0% 匹配
**状态**:邮件已发给数据同事,等修复或 backfill 计划

### 卡点 2:TW `attribution_order` 缺历史数据
**现象**:订单级表只有 2026-04-28 至 2026-05-04 共 7 天数据,33K 行。
**证据**:
- `_synced_at` 只有 2026-05-05 一个批次,无持续 backfill 迹象
- 同 schema 下 `attribution_order_click` 有 10 个月数据,但只是"7 天订单关联的历史 click",不是"10 个月订单"
**业务影响**:dashboard YoY 对比至少需要 12 个月历史
**状态**:邮件已发,等 backfill 计划

---

## 🎯 下一步具体行动(等数据期间不闲着)

### 优先级 1:Track 3 — DQ 框架代码骨架(2-3 天)
**0 返工风险**(纯代码,跟数据无关)
- [ ] 创建 `metrics-service/data_quality/` 文件夹
- [ ] 写 YAML 配置 schema(支持 not_null / unique / range / freshness)
- [ ] 写 4 个 checker 类
- [ ] 写 runner(读 YAML → 执行 → 输出报告)
- [ ] Demo 用例 + README

### 优先级 2:Track 1 收尾 — 写盘点文档(半天)
**极小返工**(只需修改"数据是 Appaman"为"32Degrees")
- [ ] `docs/existing_data_inventory.md`
- [ ] 13 张表的字段清单 + 粒度 + 用途
- [ ] Open Issues 章节(写卡点 1 / 卡点 2)

### 优先级 3:Track 2 — 星型模型框架级设计(2 天)
**框架级 0 返工,字段级等数据**
- [ ] 反推 PBI dashboard 业务需求
- [ ] 框架级 ER 图(几个 fact / 几个 dim,不细化字段)
- [ ] SCD 策略决定
- [ ] 设计文档骨架,字段细节留 TODO

### 等数据修好后(预计 1-2 周后):
- [ ] Track 2 字段级补充
- [ ] 启动 Phase 2B/3:数仓建模

---

## 📌 重要提醒(给 Claude 在新 chat 开始时)

- 用户(Sia)是 non-tech 友好的,代码要给完整版,命令要解释清楚
- 用户用 Windows + PowerShell + VS Code
- 用户在 Project 文件夹路径:`C:\Users\sia.song\analytics-platform`
- 用户 GitHub:https://github.com/sichensong-99
- 已选定方案不要再翻盘,有疑问参考 PROJECT_CONTEXT.md 的 Decision Log
- **任何建议必须用 NORTH_STAR.md 的 5 大原则过滤一遍**

---

## 🔄 进度更新历史

| 日期 | 完成内容 | 下一步 |
|---|---|---|
| 2026-04-28 | Phase 2A 完成,Project Brain 搭建完成 | 进入 Track 1 |
| 2026-05-05 | Track 1 数据探索完成,发现 2 个上游数据问题并发邮件,业务主体确认为 32Degrees | 阻塞期推进 Track 3(DQ 框架),Track 2(框架级设计),Track 1 文档收尾 |

---

## 💎 简历素材沉淀(2026-05-05 新增)

**Data Onboarding Validation & Cross-team Coordination**

在 Databricks 多源数据接入阶段,主导跨源数据一致性校验,识别出两处影响下游建模的关键问题:

1. **Source store 配置错误**:通过 5 维证据(domain / vendor / order ID 格式 / 跨源 join 匹配率 / 关键词搜索)定位 Fivetran Shopify connector 误连至同公司另一品牌 store,推动数据接入方修复 connector 配置

2. **历史数据缺失**:通过区分订单级表与点击级表的语义差异,识别出订单 fact 表 backfill 缺失,而非整 pipeline 时间窗口问题,推动 12 个月历史数据 backfill

输出标准化数据质量报告与上下游协作沟通,避免下游数仓建模基于错误源系统启动。

**关键词**:Data Source Validation / Multi-source Reconciliation / Data Onboarding QA / Cross-team Stakeholder Communication

**Data Quality Framework(2026-05-13 新增)**

设计并实现 YAML 配置驱动的数据质量校验框架,作为多源数据 pipeline 的质量门控(quality gate):

- **架构**:基于抽象基类(BaseChecker)+ Checker 注册表的可扩展设计,新增 check 类型 0 改动 runner
- **能力**:支持 4 类校验(not_null / unique / range / freshness),涵盖完整性、唯一性、值域、新鲜度
- **配置驱动**:业务方修改 YAML 即可新增校验,无需 Python 改动;运维与业务规则解耦
- **报告**:支持 console(人读)和 JSON(机器读)双格式输出,便于 pipeline 集成与告警
- **可测试**:15 个测试场景覆盖单元与端到端流程,Mock-first 设计便于本地快速迭代

**关键词**:Data Quality / Configuration-Driven Architecture / YAML DSL / Pipeline Quality Gate / Extensible Framework Design