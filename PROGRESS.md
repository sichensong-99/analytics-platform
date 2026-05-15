# Project Progress

> Last updated: 2026-05-15
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
- 数据接入工具确认:Shopify 走 Fivetran,TW 走 custom pipeline

### 数据接入校验与协调(2026-05-05 至 2026-05-15)
- ✅ Fivetran Shopify connector 错连 Appaman → 已修复至 32Degrees(8 日累计差异 0.5%)
- ✅ TW `attribution_order` backfill 多轮完成 → **2026-05-15 验证通过,全部月份 ≥ 99.85% match rate**
- ✅ 跨源 join 健康基线确认为 ≥ 99%(之前误判的 44% / 22% / 27% 是数据未完整时的伪基线)
- ✅ Source reconciliation 验证:Databricks Shopify vs Panoply 8 日累计差异 0.5%

### Track 3:DQ 框架代码骨架(2026-05-13 完成)⭐
- 基于抽象基类的可扩展架构(BaseChecker)
- 4 种 checker:not_null / unique / range / freshness
- YAML 配置驱动(2 个示例:shopify_orders, tw_attribution)
- Runner + Reporter(console + JSON 双格式输出)
- 15 个测试场景全部通过
- 位置:`metrics-service/data_quality/`
- 已推送到 GitHub

### Track 1 文档 — `existing_data_inventory.md`(2026-05-14 完成 Step 1-3)
- ✅ Section 1: Executive Summary
- ✅ Section 2: Shopify 8 张表详解
- ✅ Section 3: TW 5 张表详解
- ✅ Section 4: 其他 Schema 边界声明(扫了 8 个相关 schema,明确不纳入)
- 🚧 Section 5: PBI Dashboard 映射(下一步做)
- ✅ Section 6: Open Issues(4 个 issues,每个含根因 + 影响 + 解决方案)
- ✅ Section 7: Appendix(5 个可复用 SQL)
- 位置:`docs/existing_data_inventory.md`

### Panoply Legacy 反向工程(2026-05-15 完成 95%)⭐⭐

**起因**:在做 Track 1 文档 Step 4(PBI Dashboard 映射)时,意识到必须先完整理解过去在 Panoply 做的 ETL 体系,才能准确映射到新平台。

**产出**:`docs/legacy_panoply_etl.md`(v3,~780 行)
- 📋 完整盘点 6 大业务域、~30 张 query model 表
- ⭐ 识别出 13 个工程亮点(简历金句种子)
- 📊 提供"Legacy → New Platform"演进映射方案
- 💼 起草 11 个英文简历 Bullets + 2 个 STAR 面试故事

**6 大业务域**:
1. 销售归因(行级 + 订单级双粒度)
2. 退货分析(双路径)
3. 替换分析(双路径)
4. 运费成本
5. 订单篮子行为
6. 产品主数据 + Basket

**13 个工程亮点**(详见 `legacy_panoply_etl.md` §0.2):
1. GA4 transactionId 多键三路 join 兜底
2. sku → item_description 双路径降级匹配
3. Schema Evolution 兼容(老 tags + 新 metafield 双路径并行)⭐⭐
4. 20+ CASE WHEN 业务规则标签分类引擎
5. Responsibility 归因模型(WAREHOUSE / SHIPPING / 32D)
6. REGEXP_EXTRACT 从自由文本反推 original_order
7. PERCENTILE_CONT 日级中位数(对抗长尾偏倚)
8. GA4 `__updatetime` 最新版本去重(SCD pattern)
9. 手工 monthly CSV(freight)整合到 Lakehouse
10. 时区统一处理(`processed_at - 5h`)
11. 双粒度并行建模(行级 + 订单级 fact)— Kimball grain 原则 ⭐⭐
12. 时间分片数据源切换(GA UA → GA4 平滑迁移)
13. BI 逻辑下沉数据层(DAX → conformed dim)⭐

**剩余 5%**:其他 PBI page 的底层数据来源 — 不阻塞 Phase 2B/3,可在 Section 5 边做边补

---

## ✅ 阻塞解除(2026-05-15)

### TW 历史数据已完成 backfill,Phase 2B/3 阻塞正式解除 🚀

**验证结果**(`existing_data_inventory.md` Appendix A.2 测试 SQL):

| 月份 | Shopify 订单 | TW 匹配订单 | Match Rate |
|---|---|---|---|
| 2025-07 | 167,936 | 167,879 | 99.97% ✅ |
| 2025-08 | 145,122 | 145,066 | 99.96% ✅ |
| 2025-09 | 149,185 | 149,136 | 99.97% ✅ |
| 2025-10 | 285,692 | 285,630 | 99.98% ✅ |
| 2025-11 | 382,789 | 382,587 | 99.95% ✅ |
| 2025-12 | 428,289 | 427,636 | 99.85% ✅ |
| 2026-01 | 329,478 | 329,340 | 99.96% ✅ |
| 2026-02 | 171,854 | 171,822 | 99.98% ✅ |
| 2026-03 | 167,712 | 167,684 | 99.98% ✅ |
| 2026-04 | 146,929 | 146,888 | 99.97% ✅ |
| 2026-05 | 72,680 | 72,657 | 99.97% ✅ |

**全部 11 个月 match rate ≥ 99.85%,远超 90% 阈值。Phase 2B/3 阻塞正式解除。**

**业务意义**:
- 跨源 join 健康基线确认为 **99%+**(之前误判的 44% / 22% / 27% 缺口都已澄清)
- TW 实际追踪所有 Shopify 订单(含 direct/unattributed,channel 标记为 'direct')
- 可以正式启动数仓建模

---

## 🎯 下一步具体行动

### 立刻做(本周完成):Section 5 — 第一个 PBI Dashboard 映射

**目标 page**:`Style-channel (quantity)`(PBI 最大 report 的第 2 个 tab)

**为什么做这个**:
- ✅ 这是 Phase 2B/3 数仓建模的**需求圣经**(没有它就是不画图纸盖房子)
- ✅ "需求分析 + 反向工程"是 DE 软实力,简历核心素材
- ✅ Leader 验收的依据(新 dashboard 至少要 cover 现有功能)
- ✅ 完成第 1 个 page 后,后面 19 个 page 速度会指数提升(共用 fact)
- ✅ 0 返工风险

**已确认的关键信息**:
- 该 page 的核心数据源:PBI 里的 `Style_selling_df`(来自 Panoply 的 `Style_selling_dfNEW`)
- 该 page 没有用到 `QuantityParam` / `Threshold` 滑块
- 该 page 的用户:**整个 ecom 团队共用**(buyer 看补货、marketing 看渠道、merchandiser 看选品)
- 该 page 的位置:整个 PBI Report 第 2 个 tab(共 20+ tabs)

**操作方式**:
- 在新 chat 里告诉 Claude "开始 Section 5,从 Style-channel (quantity) page 开始"
- 提供 page 上每个 visual 的清单 + 业务用途
- Claude 帮写 `docs/existing_data_inventory.md` Section 5.1

**预计时间**:1-2 天(第 1 个 page);后续每个 page 0.5-1 天

### 之后做:

1. **Section 5 全部完成后**(~2 周)
   - 带着 Section 5 找 Leader 对齐 5 个口径决策(见 `legacy_panoply_etl.md` §10)

2. **Track 2:星型模型设计**(2-3 天)
   - 基于 Section 5 的需求 → 设计 fact + dim
   - Mermaid 画星型模型 ER 图

3. **Phase 2B/3:Databricks 数仓建模**(3-4 周)— 大头
   - ODS / DWD / DWS 三层
   - 5 个 PySpark notebooks
   - 这是简历核心素材

---

## 📌 重要提醒(给 Claude 在新 chat 开始时)

### 项目基础信息
- 用户:Sia(GitHub: sichensong-99)
- 公司:32Degrees(保暖服装品牌,2025-07-01 启用 Triple Whale)
- 项目路径:`C:\Users\sia.song\analytics-platform`
- 环境:Windows 11 + PowerShell + VS Code
- 风格:中英文混用,代码要完整版,命令要解释清楚,决策要明确推荐

### 数据源现状
- **Shopify** @ `mvdevdatabricks.shopify_32degrees`:✅ 完全 ready(2.4M 订单)
- **TW** @ `mvdev_federated_catalog.triple_whale`:✅ **完全 ready**(全部月份 ≥ 99.85% match rate)
- **ERS 产品主数据**:✅ 已在 Databricks(Sia 上传)
- **数据完整性判定标准**:跨源 monthly match rate ≥ 90%(实际达到 99%+)

### 已锁定的关键决策(不要翻盘)
- Shopify 走 Fivetran,TW 走 custom pipeline
- TW 必须走 Databricks(不直连应用层)
- 数据源边界 = Shopify + TW + ERS(其他 schema 不纳入)
- 项目数据起点 = 2023-07-01(2023/7/1 之前的 GA UA 历史不纳入)
- 数据接入工具理解:`mvdev_federated_catalog` 不是真的 federation,只是命名误导

### 工作原则
- **任何建议必须用 NORTH_STAR.md 的 5 大原则过滤一遍**
- 已选定方案不要再翻盘,有疑问参考 PROJECT_CONTEXT.md 的 Decision Log
- 用户偏好"先想清楚再动手",所以先讲全局规划再讲细节
- 用户严格反对返工,所以建议必须区分"0 返工"和"可能返工"
- 用户容易信息过载,Claude 要主动控制信息密度,**一次给一个具体任务**,不要无限发散

### 关键文档清单
- `NORTH_STAR.md` — 最高决策原则
- `PROJECT_CONTEXT.md` — 项目背景、架构、决策
- `ROADMAP.md` — 阶段计划
- `PROGRESS.md` — 本文档,当前进度
- `SIA_PROFILE.md` — Sia 偏好
- `streaming_module_plan.md` — Phase 4.5 计划
- `docs/existing_data_inventory.md` — Track 1 数据资产盘点
- `docs/legacy_panoply_etl.md` — Panoply 反向工程(13 个简历亮点的金矿)⭐

---

## 🔄 进度更新历史

| 日期 | 完成内容 | 下一步 |
|---|---|---|
| 2026-04-28 | Phase 2A 完成,Project Brain 搭建完成 | 进入 Track 1 |
| 2026-05-05 | Track 1 数据探索完成,发现 2 个上游数据问题并发邮件,业务主体确认为 32Degrees | 阻塞期推进 Track 3 |
| 2026-05-13 | Shopify 数据修复完成;TW backfill 至 2025-07-01(11-2 月仍有缺口);Track 3 DQ 框架完成并推送 GitHub | 启动 Track 1 文档 |
| 2026-05-14 | Track 1 文档 Step 1-3 完成(Section 1-4, 6, 7);TW 二次 backfill 完成 10-12 月,但 1-2 月仍缺;已发 follow-up 邮件给 Cal | Track 1 文档 Step 4(PBI Dashboard 映射) |
| 2026-05-15 | TW 数据 backfill 完成验证,全部月份 ≥ 99.85% match rate;Panoply Legacy 反向工程 95% 完成,产出 `legacy_panoply_etl.md` v3;识别 13 个简历亮点 | 启动 Section 5(从 Style-channel quantity page 开始) |

---

## 💎 简历素材沉淀

### Data Onboarding Validation & Cross-team Coordination(2026-05-05 至 15)
在 Databricks 多源数据接入阶段,主导跨源数据一致性校验:
- 通过 5 维证据定位 Fivetran connector 误配置,推动修复
- 识别 TW 历史数据 backfill 缺口,推动多轮 backfill 直至完整
- 建立可量化的"数据完整性"判定标准(跨源 month-level match rate ≥ 90%,实际达到 99%+),取代主观判断
- 实施 source reconciliation(Databricks vs Panoply,8 日累计差异 0.5%)
**关键词**:Data Source Validation / Multi-source Reconciliation / Cross-team Coordination / Quantitative Completeness Criteria

### Data Quality Framework(2026-05-13)⭐
设计并实现 YAML 配置驱动的数据质量校验框架:
- 抽象基类 + 4 种 checker(not_null / unique / range / freshness)
- YAML 驱动,业务方 0 代码改动即可新增校验
- Console + JSON 双格式报告输出
- 15 个测试场景覆盖单元 + 端到端流程
**关键词**:Data Quality / Configuration-Driven Architecture / YAML DSL / Extensible Framework Design

### Data Asset Inventory & Boundary Documentation(2026-05-14)
系统性盘点 Databricks 数据资产:
- 完整数据字典(13 张表,按业务域分类)
- 明确数据源边界(扫描 8 个周边 schema,逐一记录不纳入决策)
- 4 个 Open Issues 四段式记录(现象→根因→影响→解决方案)
- 5 个可复用 SQL 沉淀为 Appendix
**关键词**:Data Asset Inventory / Data Cataloging / Scope Documentation / Root Cause Analysis

### Legacy Panoply ETL Reverse Engineering(2026-05-15)⭐⭐
完整反向工程 Panoply 时代的 ETL 体系,作为新平台数仓建模的需求圣经:
- 盘点 ~30 张 query model,识别 6 大业务域(销售归因 / 退货 / 替换 / 运费 / 篮子行为 / 产品主数据)
- 识别 13 个工程亮点(从单一原子技巧到系统级设计)
- 起草 11 个英文简历 Bullets + 2 个 STAR 面试故事
- 提供"Legacy → New Platform"演进映射方案
- 详见 `docs/legacy_panoply_etl.md`
**关键词**:Legacy System Reverse Engineering / Multi-grain Modeling / Schema Evolution / Business Rule Refactoring / BI Layer Decoupling / Kimball Methodology

**核心亮点**(可直接用于简历英文 bullet,详见 `legacy_panoply_etl.md` §8.2):
1. **Multi-key Resolution**:GA4 transactionId 三路 join 兜底
2. **Graceful Degradation Entity Resolution**:sku → item_description 双路降级
3. **Schema Evolution Backward Compatibility**:老 tags + 新 metafield 双路径并行
4. **Multi-grain Fact Modeling**:行级 + 订单级双 fact 表(Kimball 原则)
5. **Temporal Data Source Switching**:GA UA → GA4 平滑迁移
6. **BI Layer Decoupling**:DAX 构造下沉到数据层
