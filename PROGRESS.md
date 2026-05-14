# Project Progress

> Last updated: 2026-05-14
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

### 数据接入校验与协调(2026-05-05 至 2026-05-14)
- ✅ Fivetran Shopify connector 错连 Appaman → 已修复至 32Degrees(8 日累计差异 0.5%)
- 🟡 TW `attribution_order` 1-2 月数据缺口 → 已发邮件给 Cal,等回复(其他月份 92-99% match rate)
- ✅ 跨源 join 健康基线确认为 ≥ 90%(之前误判的 44% 是数据未完整时的伪基线)
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
- 🚧 Section 5: PBI Dashboard 映射(待做 Step 4)
- ✅ Section 6: Open Issues(4 个 issues,每个含根因 + 影响 + 解决方案)
- ✅ Section 7: Appendix(5 个可复用 SQL)
- 位置:`docs/existing_data_inventory.md`

---

## ⏳ 当前阻塞(2026-05-14)

### 卡点:TW `attribution_order` 2026-01 和 02 月数据缺口

**现象**:
- 2026-01:Shopify 329K 订单 vs TW 73K 匹配,match rate 22.17%
- 2026-02:Shopify 172K 订单 vs TW 46K 匹配,match rate 26.73%
- 其他月份(2025-07 至 2026-05)match rate 均 ≥ 92%

**状态**:邮件已发给 Cal(5/14),等回复(预计 1-2 个工作日)

**业务影响**:不阻塞 Track 1 文档与 Track 2 框架级设计;只阻塞 Phase 2B/3 真实建模

---

## 🎯 下一步具体行动

### 立刻做(0 返工):Track 1 文档 Step 4 — PBI Dashboard 映射

**做什么**:对照公司现有 PBI Dashboard,把每个图表/视觉对象映射到新数据源(Shopify / TW),记录在 `docs/existing_data_inventory.md` Section 5。

**为什么必须做**:
- 这是 Phase 2B/3 数仓建模的需求输入(知道要算哪些指标才能设计 fact/dim)
- 是 leader 验收的依据(新 dashboard 至少要 cover 现有 dashboard 的所有功能)
- 0 返工(数据源映射跟 1-2 月数据缺口无关)

**操作方式**:
- 在新 chat 里告诉 Claude "继续 Track 1 文档 Step 4"
- 打开 PBI Dashboard,逐个视觉对象描述给 Claude
- Claude 帮你写 Section 5 内容

### 之后做(等 Cal 修完 TW 1-2 月数据):

- Track 2:星型模型框架级设计(2-3 天)
- Phase 2B/3:数仓建模(3-4 周)

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
- **TW** @ `mvdev_federated_catalog.triple_whale`:🟡 2026-01/02 还有缺口,其他月份 ≥ 92% match rate
- **数据完整性判定标准**:跨源 monthly match rate ≥ 90%

### 已锁定的关键决策(不要翻盘)
- Shopify 走 Fivetran,TW 走 custom pipeline
- TW 必须走 Databricks(不直连应用层)
- 数据源边界 = Shopify + TW(其他 schema 不纳入)
- 健康 match rate 基线 = ≥ 90%(不是 44%)
- 数据接入工具理解:`mvdev_federated_catalog` 不是真的 federation,只是命名误导

### 工作原则
- **任何建议必须用 NORTH_STAR.md 的 5 大原则过滤一遍**
- 已选定方案不要再翻盘,有疑问参考 PROJECT_CONTEXT.md 的 Decision Log
- 用户偏好"先想清楚再动手",所以先讲全局规划再讲细节
- 用户严格反对返工,所以建议必须区分"0 返工"和"可能返工"

---

## 🔄 进度更新历史

| 日期 | 完成内容 | 下一步 |
|---|---|---|
| 2026-04-28 | Phase 2A 完成,Project Brain 搭建完成 | 进入 Track 1 |
| 2026-05-05 | Track 1 数据探索完成,发现 2 个上游数据问题并发邮件,业务主体确认为 32Degrees | 阻塞期推进 Track 3 |
| 2026-05-13 | Shopify 数据修复完成;TW backfill 至 2025-07-01(11-2 月仍有缺口);Track 3 DQ 框架完成并推送 GitHub | 启动 Track 1 文档 |
| 2026-05-14 | Track 1 文档 Step 1-3 完成(Section 1-4, 6, 7);TW 二次 backfill 完成 10-12 月,但 1-2 月仍缺;已发 follow-up 邮件给 Cal | Track 1 文档 Step 4(PBI Dashboard 映射) |

---

## 💎 简历素材沉淀

### Data Onboarding Validation & Cross-team Coordination(2026-05-05 至 14)
在 Databricks 多源数据接入阶段,主导跨源数据一致性校验:
- 通过 5 维证据定位 Fivetran connector 误配置,推动修复
- 识别 TW 历史数据 backfill 缺口,推动多轮 backfill
- 建立可量化的"数据完整性"判定标准(跨源 month-level match rate ≥ 90%),取代主观判断
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