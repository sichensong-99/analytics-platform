# Project Progress

> Last updated: 2026-05-13
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

### Project Brain 搭建(2026-04 完成)
- NORTH_STAR / PROJECT_CONTEXT / ROADMAP / PROGRESS / SIA_PROFILE / streaming_module_plan
- Project Instructions 配置完成

### Track 1 — 数据资产探索(2026-05-05 完成)
- 摸清 Databricks 上 13 张表的结构和粒度
  - Shopify @ `mvdevdatabricks.shopify_32degrees`:8 张表
  - TW @ `mvdev_federated_catalog.triple_whale`:5 张表
- 数据接入工具确认:Shopify 走 Fivetran,TW 走 custom pipeline

### 数据接入校验与协调(2026-05-05 至 2026-05-13)
- 发现并修复:**Fivetran Shopify connector 错连 Appaman**,推动切换到 32Degrees,已修复
- 发现并修复:**TW attribution_order 缺历史数据**,推动 Cal backfill 到 2025-07-01,已修复(但 11-2 月仍有缺口)
- 跨源 join 匹配率 44% 已确认为业务合理基线(其余为 direct/unattributed 流量)

### Track 3:DQ 框架代码骨架(2026-05-13 完成)⭐
- 基于抽象基类的可扩展架构(BaseChecker)
- 4 种 checker:not_null / unique / range / freshness
- YAML 配置驱动(2 个示例:shopify_orders, tw_attribution)
- Runner + Reporter(console + JSON 双格式输出)
- 15 个测试场景全部通过
- 完整 README + Conventional Commit 风格 commit history
- 位置:`metrics-service/data_quality/`
- 已推送到 GitHub

---

## ⏳ 当前阻塞(2026-05-13)

### 卡点:TW `attribution_order` 11月-2月 数据缺口

**现象**:2025-11 至 2026-02 这 4 个月订单量比相邻月份骤降 95%+,而这恰好是 32Degrees 旺季(寒冬 + 节日)。

**月度数据**:
- 2025-10:181,906 ✅
- 2025-11:35,984 🚩
- 2025-12:1,500 🚩🚩🚩
- 2026-01:20,090 🚩
- 2026-02:45,946 🚩
- 2026-03:167,683 ✅

**状态**:邮件已发给 Cal,要求全量 rerun backfill(2025-07-01 至今)。等回复(预计 1-2 个工作日)。

**业务影响**:不影响 Track 1/2 文档与设计;只影响 Phase 2B/3 真实建模(必须等数据完整才能动)。

---

## 🎯 下一步具体行动

### 优先级 1:Track 1 文档收尾(半天 - 1 天)— 0 返工
- 写 `docs/existing_data_inventory.md`
- 13 张表的字段清单 + 粒度 + 用途
- Open Issues 章节(写 TW 缺口,等 Cal 修完后打勾)
- Source-to-Dashboard 映射章节(PBI 视觉对象 → 新数据源)

### 优先级 2:Track 2 框架级星型模型设计(2 天)— 0 返工
- 反推 PBI dashboard 业务需求
- 框架级 ER 图(几个 fact / 几个 dim,关联关系)
- SCD 策略决定
- 字段细节留 TODO,等 TW 缺口修复

### 等 TW 缺口修复后(预计本周内):
- Track 2 字段级补充(1 天)
- 启动 Phase 2B/3:数仓建模(3-4 周)

---

## 📌 重要提醒(给 Claude 在新 chat 开始时)

- 用户(Sia)是 non-tech 友好的,代码要给完整版,命令要解释清楚
- 用户用 Windows + PowerShell + VS Code
- 用户在 Project 文件夹路径:`C:\Users\sia.song\analytics-platform`
- 用户 GitHub:https://github.com/sichensong-99
- 已选定方案不要再翻盘,有疑问参考 PROJECT_CONTEXT.md 的 Decision Log
- **任何建议必须用 NORTH_STAR.md 的 5 大原则过滤一遍**
- **当前等待 Cal 修 TW 11-2 月缺口**,不阻塞 Track 1/2,但阻塞 Phase 2B/3
- Shopify 数据已完全 ready(244 万订单,从 2025-07-01 起)
- TW 数据已 backfill 至 2025-07-01,但 11-2 月有缺口

---

## 🔄 进度更新历史

| 日期 | 完成内容 | 下一步 |
|---|---|---|
| 2026-04-28 | Phase 2A 完成,Project Brain 搭建完成 | 进入 Track 1 |
| 2026-05-05 | Track 1 数据探索完成,发现 2 个上游数据问题并发邮件,业务主体确认为 32Degrees | 阻塞期推进 Track 3 |
| 2026-05-13 | Shopify 数据修复完成;TW backfill 至 2025-07-01(11-2 月仍有缺口,已 ping Cal);**Track 3 DQ 框架完成并推送 GitHub** | 启动 Track 1 文档 / Track 2 框架级设计 |

---

## 💎 简历素材沉淀

### Data Onboarding Validation & Cross-team Coordination(2026-05-05)

在 Databricks 多源数据接入阶段,主导跨源数据一致性校验:

1. **Source store 配置错误**:通过 5 维证据(domain / vendor / order ID 格式 / 跨源 join 匹配率 / 关键词搜索)定位 Fivetran Shopify connector 误连至同公司另一品牌 store,推动数据接入方修复 connector 配置
2. **历史数据缺失**:通过区分订单级表与点击级表的语义差异,识别出订单 fact 表 backfill 缺失,推动 12 个月历史数据 backfill
3. **业务直觉驱动的二次校验**:基于保暖品牌季节性预期,发现 backfill 后仍有 4 个月旺季数据骤降 95% 的异常,推动二次 rerun

**关键词**:Data Source Validation / Multi-source Reconciliation / Data Onboarding QA / Cross-team Stakeholder Communication / Business-driven Data Sanity Check

### Attribution Coverage Analysis(2026-05-13)

在 TW 归因数据接入完成后,通过对比匹配/未匹配订单的画像(订单数、平均订单价值、总收入),识别 44% 的归因覆盖率为 DTC 业务的合理基线(剩余为直接访问与自然流量),指导后续数仓建模将 `channel='direct/unattributed'` 作为合法维度值保留。

**关键词**:Attribution Modeling / Data Coverage Analysis / Business Logic Validation

### Data Quality Framework(2026-05-13)⭐

设计并实现 YAML 配置驱动的数据质量校验框架,作为多源数据 pipeline 的质量门控:

- **架构**:基于抽象基类(BaseChecker)+ Checker 注册表的可扩展设计,新增 check 类型 0 改动 runner
- **能力**:支持 4 类校验(not_null / unique / range / freshness),涵盖完整性、唯一性、值域、新鲜度
- **配置驱动**:业务方修改 YAML 即可新增校验,无需 Python 改动
- **报告**:支持 console(人读)和 JSON(机器读)双格式输出
- **可测试**:15 个测试场景覆盖单元与端到端流程

**关键词**:Data Quality / Configuration-Driven Architecture / YAML DSL / Pipeline Quality Gate / Extensible Framework Design