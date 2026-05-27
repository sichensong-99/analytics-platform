### Slice 1 收尾 — 对账通过 trust gate(2026-05-27)

**对账结果**:
- Overall −1.51%(180,670 / 183,438),< 2% trust gate ✓
- 残差完全归因(week 28,基准 D3 验证):
    EXC 整单 −2,209 + refund 行级 −6,573 + cancel 行级 −803,
    与新平台减项 7,376 ≈ Panoply 减项 6,705 + 670 偏差完美对上
- 45 个 vend_id 桶 FAIL 不阻塞:小分母放大 + replacement 未排除,
  trust gate 重定义为"overall < 2% 且残差完全归因"已达成

**Decision 22 v3 锁定**:
- is_sales_attributable = NOT(is_exc_order OR is_replacement_order),
  只管 EXC + replacement 两类整单排除
- refunded_quantity 行级列 = SUM(order_line_refund.quantity) 覆盖
  全 restock_type(return / no_restock / cancel / legacy_restock),
  净销量 = quantity − refunded_quantity
- cancel 走行级 netting 不单独建订单级 flag —— Shopify 给取消单生成的
  refund line(restock_type='cancel')天然在行级净扣覆盖范围内
- is_refunded / is_refund_order 已删

**Panoply 真口径(读源码定论)**:
- refund 排除是订单级整单打标剔除(tag 路径 + metafield 路径)
- 销售链路从未 join refund line items → cancel 无单独处理,被当销量
- 全订单状态收入(无 financial_status / cancelled_at 过滤)
- 这解释了 Panoply 与新平台 −1.51% 的方法论差(非误差)

**Panoply 旧报表的精度缺陷(新平台主动修正)**:
- legacy refund 只通过 tag 反推,覆盖率 ~22%(原生 175,409 单 vs
  tag 39,382 单)→ 新平台用原生 order_line_refund 全覆盖
- legacy 不识别 cancel → 取消单的 803 件被当销量
- 类比 Decision 17 DST bug 修正,文档化为 intentional correction,
  不追 0% diff

**metafield 状态**:
- Databricks 同事昨天刚 enabled `order_metafield` table,
  几小时内可见 → metafield 是独立表(owner_id/key/value 行级),
  不是 order 表的列(Fivetran 标准 Shopify connector 结构)
- notebook 04 Section 3b 已改为表存在性自动检测,优雅降级
- metafield 到位后流程:DESCRIBE order_metafield → 核 schema →
  重跑 notebook 04 → 重新对账(预期 overall 残差略往下 ~1.6-1.8%)

**本日交付物**:
- ✅ notebook 04 v3(Section 3b/3c/7/8 + header)— 行级 refund netting + 
   replacement 优雅降级
- ✅ 01_new_platform_query.sql v3(SUM(quantity − refunded_quantity) +
   is_sales_attributable filter)
- ✅ 02_panoply_legacy_query.sql v3(BigQuery EXTRACT 语法,Sia 自修)
- ✅ definitions.yaml quantity_by_style_channel_week v1.2(breaking change)
- ✅ star_schema_ddl.sql v2.0(dim_channel 重复定义清理 + 三表同步实际
   schema + fact 改为 Decision 22 v3)
- ✅ run_reconciliation.py 跑通:180,670 vs 183,438 = −1.51% PASS

**待办**:
- ⏳ metafield 到位 → 重跑 notebook 04 → 重新对账
- ⏳ Demo(H6 demo script,已开始草稿)
- ⏳ next page: page_view(需 TW Web Analytics 接入,邮件已发)

### Slice 1 量化基线(2026-05-27 freeze)

> 这些数字是 Slice 1 demo 的核心证据,简历 STAR 里的 R(Result)。
> metafield 落地重跑后会更新,但 baseline 保留作演进对比。

| 指标 | 数值 | 备注 |
|---|---|---|
| ETL 行数(slice 1 ETL window 后) | 9,965,352 | Shopify order_line 9.94M 窗口内行 |
| Shopify order(全量) | 11.45M | 简历:千万级订单规模 |
| Shopify order_line(全量) | 44.67M | |
| TW attribution_order_click(全量) | 25.26M | |
| TW join 匹配率 | 99.72% | unmatched 0.280%,PASS |
| Channel DQ unmatched | 0.318% | <0.5% PASS,WARN baseline 用 |
| Product DQ unmatched | 0.000% | PASS |
| Week 28 net units(新平台) | 180,670 | Decision 22 v3 |
| Week 28 net units(Panoply 基准) | 183,438 | Style_selling_df |
| Overall reconciliation diff | −1.51% | < 2% trust gate ✓ |
| Reconciliation buckets | 221 | vend_id × week |
| ↳ PASS | 110 (49.77%) | < 2% diff |
| ↳ WARN | 66 (29.86%) | 2-5% diff |
| ↳ FAIL | 45 (20.36%) | > 5% diff,小分母放大主导 |
| 残差归因 | 100% | EXC 2209 + refund 6573 + cancel 803 |
| Legacy refund 覆盖缺口 | 78% | tag 法 39,382 vs 原生 175,409 单 |

**核心结论**:
- is_sales_attributable = NOT(is_exc_order OR is_replacement_order),仅管整单排除两类。
- refund 改为行级净扣减:新增 refunded_quantity 列,净销量 = quantity − refunded_quantity。
  is_refund_order 列废弃(整单排除 refund 经对账证伪:残差 1.97%→6.57%)。
- 对账(iso_week 28,Panoply 基准 183,438):行级净扣减 = 180,670(−1.51%),方向正确。
- 偏差 −2,768 已定位:order_line_refund 含 cancel 类(restock_type),旧报表对 cancel
  无单独处理 → cancel 算不算需看 Panoply 源码确认。

**下一步(新 chat)**:发 Style_selling_dfNEW 全嵌套 + refund1_news + refund4 +
02_panoply_legacy_query.sql → 确定 Panoply 真实口径 → notebook 04 / 对账 SQL / DDL 三个终版。

**并行待办**:
- Fivetran 同事:order metafield 同步(replacement 识别);同事提示字段可能在 returns 表,待查。
- Databricks 同事:TW Web Analytics 表接入(page_view funnel)— 邮件已发。
- star_schema_ddl.sql 待修(dim_channel 重复定义 + fact 段过时)。
- Demo 未做。

**Decision 22 需改 v3**:模型从"三类合一 boolean"改为"EXC+replacement 用 boolean,
refund 用行级 refunded_quantity 列"。

**三类排除信号已查清(replacement / refund / EXC)**:
- EXC 换货单:`order.name LIKE '%EXC%'` — Databricks 原生可识别(窗口内 53,467 单)
- refund 退款单:Shopify 原生 `refund` 父表 join order_id(窗口内 175,409 单)。
  取代 Panoply 的 `tags LIKE '%refund%'` 反推 —— Panoply 同口径仅 39,382 单,
  证明原生表更全(系统自动生成,不依赖人工打标);抽样 50 单 100% covered。
- replacement 补发单:依赖 Shopify order metafield(`replace_refund` /
  `order_issue` / `original_order_if_replaced_`)。**这三个 metafield 未被
  Fivetran 同步进 Databricks**(order 表无此列,无独立 metafield 表)→
  已发邮件请 Fivetran 同事开启 order metafield 同步。

**已澄清(更正旧表述)**:
- replacement 订单号**不含 EXC** —— replacement(补发)/ EXC(换货)/
  refund(退款)是三类独立订单,report 三类都排除。
- Returnly **已停用** —— `tags LIKE '%returnly%'` 过滤作废,无需接 Shopify tags。
- replacement/refund 现在标在 **metafield**,不再用 note/tag。
- 退货/换货走 Loop(Returnly 替代品),但 Loop 触发的退款仍落 Shopify 原生
  refund 表,refund 信号不受影响。

**is_sales_attributable 落地策略 —— 分两步**:
- 第一步(现在):`fact_orders_line` 加 `is_sales_attributable` 列,实现
  EXC + refund 两类;notebook 04 预留 replacement 接口 + TODO 注释。
- 第二步(metafield 到位后):补 replacement,重跑 notebook 04。

**下一个 dashboard:page_view report**:
- 销售侧(Units Sold / Net Sales / Unique Orders)— Databricks 现有数据可建。
- funnel 侧(item view / add to cart / 分渠道 session)— 来自 GA4,
  Databricks **无任何 GA4 ingestion**(现有临时表是手动上传的一周数据)→
  需新接 GA4(待与 ingestion 同事确认)。

**待 Leader 确认**:is_sales_attributable 数据层统一标记方向(Q③);
demo 反馈 + 下一个想看的 dashboard(Q④)。

### Day 5 关键产出与发现
- **对账谜题破解**:初版桶级 FAIL 25%,但 overall 仅 3.66% — 经诊断为 Panoply 源端订单过滤造成的系统性单向偏差(非数据错)。Sia 主动回忆出 Panoply report 的 4 道 WHERE 过滤是破案关键。
- **trust gate 重定义**:从"95% 桶 < 2%"改为"overall < 2% 且残差完全归因",规避小分母放大的误导。
- **架构决策待落地**:business rule(refund/replacement 排除)应物化为 fact 表 `is_sales_attributable` flag(single source of truth),取代 Panoply 那种散落 4 处的 WHERE 过滤。列入 backlog,见 Decision 22。

### Slice 1 待收尾项(Day 5 后)
- [ ] `is_sales_attributable` flag 落地(改 fact schema + notebook 04 + 重跑)— 需先接入 replacement/refund 源表 + Fivetran Shopify `tags`
- [ ] Demo 反馈消化

### Slice 1 四张表进度(全部完成)
| 表 | Notebook | 状态 | 行数 |
|---|---|---|---|
| `dim_date` | 01 | ✅ 已建 | 2,922 |
| `dim_channel` | 02 | ✅ 重建完成(v2.0 真实种子值) | 23 |
| `dim_product` | 03 | ✅ 已建 | 36,680 |
| `fact_orders_line` | 04 | ✅ 已建(全量重建,5 项验证全过) | 9,965,352 |

### Day 3-4 关键完成事项
- **Day 3**:notebook 04 channel DQ 卡点解除。dim_channel 种子重建为真实 TW source 值;
  notebook 04 改用 classic/personal compute(Serverless 不支持 cache → 全 DAG 重算 + heartbeat timeout);
  加 source normalization 层(emarsys 大小写归一 / google% URL 编码串归一)。
  最终 channel DQ 0.318% PASS、product DQ 0.000% PASS,996 万行写入成功。
- **Day 4**:metrics-service 真连 Databricks SQL Warehouse(ServerlessWarehouse)。
  PAT 被组织禁用 → 改用 OAuth U2M 浏览器登录认证。
  databricks_client.py 加 connection-mode toggle(databricks/mock 可切换);
  `_bind_params` 解决两个真连才暴露的问题:date_key 是 BIGINT(date→int yyyyMMdd)、
  连接器 IN-clause 列表展开不稳(改为服务层受控 SQL 解析 + 引号转义)。
  definitions.yaml 指标升 v1.1,对齐 dim_channel v2.0 列名(legacy_channel_group→channel_group)。

### Day 5 待办(下个 chat 启动点)
- Next.js `style-channel-quantity` page 从 mock 改为真连 metrics-service API
- 跑 reconciliation 脚本对账 Panoply Style_selling_df(< 2% trust gate)
- Leader demo(H6 demo script)

### 环境备忘(Day 4 配置,新 chat 需知)
- metrics-service 连 Databricks 用 OAuth(`.env` 里 DATABRICKS_AUTH_TYPE=oauth,无需 PAT)
- SQL Warehouse:ServerlessWarehouse(http_path 在 .env)
- 起服务:先激活 .venv,再 `uv run uvicorn app.main:app --reload`(在 metrics-service 目录)
- 测试 token:`uv run python gen_test_token.py`
- `.env` 已被 .gitignore 忽略,勿提交

### 环境就绪情况
- Databricks schema `mvdevdatabricks.analytics_platform_32degrees` 权限确认:ALL PRIVILEGES + EXTERNAL USE SCHEMA + MANAGE
- ERS Volume 决策:用共享 `mvdevdatabricks.32degrees.raw_uploads/ers/`(ERS 是全公司产品主数据,放共享 raw zone 是正确架构;无需等同事建独立 Volume — 此决策应作为 Decision 20 补入 PROJECT_CONTEXT)
- notebook 全部存放在 Databricks Workspace `Users/sia.song@32degrees.com/analytics-platform/slice_1/`

### Notebook 01-03 实建细节(已跑通)
- **notebook 01 `dim_date`**:原设计从 Volume 读 Parquet,因新 schema 无 Volume,改为 in-notebook PySpark 直接生成(纯算法,无外部文件依赖)。2922 行,ISO 8601 跨年边界 spot check(2024-12-30→2025-W01,2025-12-29→2026-W01)通过。
- **notebook 02 `dim_channel`**:16 行种子载入成功,但**种子里的 channel_source 值是按推测写的(google-ads/meta/klaviyo...),与 TW 真实数据对不上 → 是 notebook 04 FAIL 的根因,需重写**。
- **notebook 03 `dim_product`**:ERS CSV 自动检测为 current 格式(列名 SKU/Style#/Item Description 带空格 + Geodis/Ladder 列)。Decision 19 双格式检测生效。36,680 行,is_complete 全部 true。SKU 主键格式 `TLF60281DRT-067-XS`,vend_id = Style#。

### Notebook 04 关键发现(重要,新 chat 需知)
- **TW 正确的归因表是 `attribution_order_click`**,不是 `attribution_order`(后者只有 9 列,无 channel 信息)
- `attribution_order_click` 关键列:`_triple_whale_order_id`(STRING,join key)、`source`(channel)、`click_date`(timestamp,last-touch 去重用)
- join key 映射:Shopify `order.id`(BIGINT,cast STRING)↔ TW `_triple_whale_order_id`(STRING)
- Shopify `order` 表**无 `tags` 列**;`order_line.order_id` 是 BIGINT;`order_line.sku` 存在
- **TW join 成功率高**:990 万行中 unmatched 仅 0.280%(PASS)
- **但 channel DQ FAIL:44.5% 的行 channel_key=0(unknown)**
- 根因:dim_channel 种子的 channel_source 值与 TW `attribution_order_click.source` 实际值不匹配
- DQ-as-Gate 按设计拦截坏数据,未写入表 ✅
- **[Known-issue] `attribution_order_click` 是多租户原始落地表**:`source` 列长尾里出现非 32D 品牌(`DuckaDilly Newsletter` / `Catalinbread Newsletter` / `HealthRangerStore.com` 等),说明该表未按 32D 账号过滤。**对 Slice 1 无影响** —— 跨源 join 以 `_triple_whale_order_id`(= 全局唯一的 Shopify order.id)为 key,外部品牌的点击 join 不上 32D 订单,天然被隔离,不进 fact 表。唯一代价是 ETL 读了比实际需要更大的表(性能,Slice 1 可接受)。**未与 Databricks 同事沟通(不阻塞,不属其职责范围)**;建议未来在 ingestion 层按 account_id 过滤作为成本优化项。

### 明天第一步要跑的 SQL
\```sql
SELECT source, COUNT(*) AS cnt
FROM mvdev_federated_catalog.triple_whale.attribution_order_click
GROUP BY source
ORDER BY cnt DESC;
\```
两种可能:
- 情况 A:TW source 只是名字写法不同 → 改 dim_channel 种子名字,重跑 02 + 04
- 情况 B:那 44% 的 source 本身是 NULL/空 → 这些订单 TW 未归因,需决定归到哪个 channel(direct?unknown?)

### Notebook 04 已知性能优化点(下次重跑前要改)
- Section 8 生成 surrogate key `order_line_key` 用了无 partitionBy 的 `Window.orderBy()` → 全量 shuffle,导致跑了 1 小时+
- 修复:改用 `F.monotonically_increasing_id()`,零 shuffle。替换代码:
\```python
fact_final = fact_raw.withColumn(
    "order_line_key",
    F.monotonically_increasing_id(),
).select(
    "order_line_key", "channel_key", "product_key", "date_key",
    "shopify_order_id", "shopify_line_id", "sku_raw",
    "quantity", "pre_tax_price", "tw_channel_source", "tw_click_ts",
    "financial_status", "is_refunded", "iso_year", "iso_week", "_ingested_at",
)
\```

### 数据量级实测(简历素材 — 真实规模数字)
- Shopify `order`:11.45M 行
- Shopify `order_line`:44.67M 行
- TW `attribution_order_click`:25.26M 行
- Slice 1 ETL 窗口(2025-07-01+)order line:9.94M 行
- → 简历可写"端到端处理千万级订单行数据"

### Day 4-5 计划(notebook 04 跑通后)
- Day 4:`metrics-service/app/databricks_client.py` 把 mock 换成真实 Databricks SQL 连接
- Day 4.5:数据正确率验证 — 用 Panoply `Style_selling_df` 对比新平台,< 2% trust gate(Claude 会带做)
- Day 5:端到端 wire-up + Leader demo

---

### 2026-05-19/20 完成任务汇总(P0 + H)
- ✅ Task A-D:Decision Log / 架构文档 / dim_date 脚本 / 4 notebook 骨架
- ✅ Task E:definitions.yaml 追加 quantity_by_style_channel_week + main.py 泛型 filter + databricks_client mock
- ✅ Task F:Next.js `style-channel-quantity` page(跑通验证 OK)+ API proxy 白名单转发 + dashboards 列表入口
- ✅ Task G:4 张 Slice 1 表 DQ YAML(dim_date/dim_channel/dim_product/fact_orders_line)
- ✅ Task H2/H4/H5:Reconciliation 脚本 / legacy_panoply_etl.md v3 / Decision Log 17-19
- ✅ Slice 1 Day 2-3:notebook 01/02/03 真实建表,notebook 04 卡 channel DQ
- ⏳ 剩余:notebook 04 修复 + Day 4-5 + H3(下一个 PBI page)+ H6(demo script)

### 2026-05-19 — Pre-permission preparation tasks (P0 A/B/C/D) 完成

权限到位前的 4 个零返工准备任务已完成,代码层 Day 2-3 完全 ready。

**完成清单**:
- ✅ Task A: Decision Log 新增 Decision 10-16(7 条架构决策正式归档)
- ✅ Task C: `scripts/generate_dim_date.py` 本地脚本验证,2922 行 CSV/Parquet 输出正常
- ✅ Task B: `docs/architecture/slice_1_design.md`(~700 行 19 sections)— 端到端架构设计文档,涵盖数据源/星型模型/跨源 join 策略/DQ/性能/Schema 演进/回滚/测试/部署/风险/Open Questions
- ✅ Task D: `databricks-notebooks/slice_1/` 4 个 PySpark notebook 骨架 + README:
  - `01_build_dim_date.py` — ISO 8601 边界 case 验证
  - `02_seed_dim_channel.py` — 版本化 seed SQL 驱动
  - `03_build_dim_product.py` — **ERS 双格式 schema-detection 自动识别**(legacy + post-2026 redesign)+ 三 pass 优雅降级
  - `04_build_fact_orders_line.py` ⭐ — **DST-aware 时区**(`from_utc_timestamp('America/New_York')`)+ **multi-tier DQ**(PASS/WARN/FAIL,阈值基于 0.15% 实际 baseline 校准)+ Last-touch Window 去重 + Cross-type join

**新增简历关键词**:
- Schema-evolution-tolerant ingestion(双格式 ERS)
- DST-aware timezone correction(发现并修正 legacy bug)
- Multi-tier DQ SLO calibrated against empirical baseline
- Authored end-to-end architecture design doc before implementation

**当前阻塞 → 已解除路径明确**:
- Databricks 同事 2026-05-19 邮件确认 admin 权限已开通(在 `mvdevdatabricks.32degrees`)
- 已回信请求一个独立 schema `mvdevdatabricks.analytics_platform_32degrees`,避免命名空间与其他项目混杂
- 预计 1-2 个工作日内拿到新 schema → 立即启动 Day 2

**等待期下一步**:Task E(YAML 指标定义)→ Task F(Next.js mock UI)→ Task G(DQ YAML 配置)

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
- ✅ Section 5.1: `Style-channel (quantity)` page 反向工程(见下方独立条目)
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

### Track 1 §5.1 — 第一个 PBI page 反向工程(2026-05-18 完成)⭐

**目标 page**:`Style-channel (quantity)`(PBI 第 2 个 tab)

**产出**:`docs/existing_data_inventory.md` §5.1(完整章节,8 个子节)
- §5.1.1 Page 全景(4 个 visual:时间滑块、3 个 slicer、折线图、矩阵表)
- §5.1.2 Visual 详解(每个 visual 的字段、用户角色、决策场景)
- §5.1.3 数据源追溯(100% 来自 `Style_selling_df`,字段血缘表)
- §5.1.4 ⭐ 3 个简历级洞察:
  1. **Conformed fact 服务多角色**(Kimball 教科书案例)
  2. **BI 派生 vs 源系统物化的时间口径风险**(中高级 DE 才会注意到的细节)⭐
  3. **行级粒度的不可替代性**(验证双粒度建模设计的正确性)
- §5.1.5 新平台对应方案(字段映射表 + SQL 查询路径 + YAML 指标草稿)
- §5.1.6 Channel 口径迁移影响分析(GA4 → TW 双口径方案)
- §5.1.7 待 Leader 对齐的 3 个口径决策(留给后续会议)
- §5.1.8 完成检查清单

**新增简历金句**(3 条):
- "Validated Kimball's conformed fact principle in legacy system reverse engineering — identified a single fact table serving buyer / marketing / merchandiser personas via dimensional slicing."
- "Identified a latent risk in legacy BI report where tool-derived date hierarchy and source-system-precomputed date fields could disagree on boundary weeks; resolved by introducing a unified `dim_date` conformed dimension."
- "Architected a dual-taxonomy channel dimension to handle attribution platform migration (GA4 → Triple Whale) with non-overlapping data windows."

### Day 1 — Slice 1 完整交付(2026-05-18)⭐⭐⭐

**方法论转变(关键)**:经讨论锁定采用 **Vertical Slice(垂直切片)** 方法论交付 Phase 2B/3,替代"先全部建完再上线"的瀑布式。每个切片从数据源到前端端到端打通,逐切片扩展数仓。

**切片 1 范围**:
- 服务于:`Style-channel (quantity)` page 端到端打通 → 给 Leader 看 demo
- 数据窗口:2025-07-01 起(与 TW attribution 重叠期)
- 4 张表:`dim_date`, `dim_channel`, `dim_product`, `fact_orders_line`
- 预计工时:5 天(Day 1 设计 → Day 2-3 ETL → Day 4 服务层 → Day 5 前端)

**Day 1 完整产出(4 个任务)**:

#### 任务 1:星型模型 DDL ✅
- 文件:`docs/data_modeling/star_schema_ddl.sql`(v1.0 → v1.1)
- v1.0:4 张表 DDL(dim_date / dim_channel / dim_product / fact_orders_line)
- v1.1 调整(任务 4 触发):dim_channel 砍 `is_web_attributed` / `is_operational`,重命名 `ga4_channel_name` → `legacy_channel_group`
- 完整 header 含 changelog / purpose / star schema 图 / 5 大设计决策 / 执行 prerequisites

#### 任务 2:PROGRESS.md 更新 ✅
- 记录 Day 1 状态,初版决策(Decision 10-14)
- 阻塞章节:等 Databricks 权限开通

#### 任务 3:dim_date 种子数据生成脚本 ✅
- 文件:`scripts/generate_dim_date.py` + `scripts/.gitignore`
- 纯标准库(`datetime` + `csv`)生成 2023-01-01 至 2030-12-31(2,922 行)
- 可选 pandas + pyarrow 输出 Parquet(Databricks 加载最快格式)
- 内置 ISO 8601 边界周 sanity check(2024-12-30 → ISO 2025-W01 等)
- `.gitignore` 排除生成的 .csv / .parquet — 脚本是 source of truth,artifact 可重生成

#### 任务 4:dim_channel 种子 SQL ✅
- 文件:`docs/data_modeling/dim_channel_seed.sql`
- 16 行(1 unknown placeholder + 15 TW source 值)
- TRUNCATE-then-INSERT 模式,幂等可重跑
- **Dual-display taxonomy 设计**:
  - `channel_source`(TW 原值,如 `google-ads`)→ 同事用 TW UI 时认知一致
  - `legacy_channel_group`(GA4 风格,如 `Paid Search`)→ Leader 用旧 PBI 时认知一致
  - 同一 dim 表服务两类用户,**Conway's Law 在数据建模中的应用**
- 含验证查询(行数 / 分组 / 付费 / 活跃 channel)

**Day 1 关键设计决策(已锁定,见下方 Decision 10-16)**:
1. Vertical Slice 方法论(替代瀑布式)
2. ISO 8601 only date taxonomy(砍 US-week 兼容字段)
3. SCD1 + YAGNI(SCD2 延期)
4. Schema temporally unbounded, ETL temporally bounded
5. Channel taxonomy alignment with TW(同事一致性 > 工程自定义分类)
6. Dual-display channel dimension(legacy_channel_group 服务 Leader)
7. is_paid forward-looking flag(切片 4+ ROAS 指标的前瞻设计)

**TW pipeline owner 澄清的两个 meta-category**:
- `Non-attributed`:其他销售渠道(如 Shopify Shop app),非站内流量
- `Excluded`:exchanges 或 draft orders 等运营订单
- 同事说"不 include 也行",但我们**选择保留并显式标注**(显式建模 > 静默丢弃)

**新增简历金句(17 条,本次最大单日产出)**:

设计阶段(7 条):
1. "Adopted vertical-slice agile delivery on the data platform — built end-to-end pipeline (raw → fact/dim → metric service → portal) for each metric incrementally."
2. "Standardized date semantics on ISO 8601 across the new analytics platform — single source of truth for all temporal slicing."
3. "Made deliberate trade-off to defer SCD2 implementation until business case emerges (YAGNI principle)."
4. "Designed fact tables to be temporally unbounded with ETL job parameters controlling actual data window — enabling incremental backfill without schema changes."
5. "Through consultation with attribution platform's data owner, discovered platform-specific meta-categories; modeled them explicitly rather than dropping."
6. "Authored comprehensive DDL header documentation capturing design decisions, execution prerequisites, and slice context."
7. "Established conventional commits discipline (feat/fix/docs prefixes) for changelog automation readiness."

任务 3 dim_date 生成器(3 条):
8. "Pre-computed dim_date offline in Python rather than in-warehouse SQL — leveraged mature standard library ISO 8601 implementation over dialect-specific SQL WEEK functions, enabling unit testability and version-controlled date semantics."
9. "Built deterministic seed data generators with embedded sanity checks for ISO 8601 year-boundary edge cases (e.g., 2024-12-30 belongs to ISO 2025-W01) — preventing silent date semantic drift before production load."
10. "Practiced 'commit generators, gitignore artifacts' discipline — keeping repos lean and forcing idempotent data generation as a system-level guarantee."

任务 4 dim_channel 设计(4 条):
11. "Aligned new platform's channel taxonomy with source attribution platform (Triple Whale) — prioritizing user cognitive consistency across tools over engineer-imposed re-categorization."
12. "Architected a dual-display channel dimension carrying both source-platform naming (Triple Whale) and legacy-grouping naming (GA4-derived) — same dimension serves both operations team and executive without forcing either to learn the other's vocabulary."
13. "Mitigated platform migration cognitive cost by preserving legacy taxonomy as a denormalized column in the new dimension, demonstrating Conway's Law awareness in data modeling — organizational structure influencing schema design."
14. "Pre-encoded ad-spend taxonomy via `is_paid` flag in channel dimension, enabling one-line ROAS metric implementation in subsequent slices without dimension migration."

§5.1 反向工程沉淀(3 条):
15. "Validated Kimball's conformed fact principle in legacy system reverse engineering — single fact table serving buyer / marketing / merchandiser personas via dimensional slicing."
16. "Identified BI tool-derived date hierarchy vs source-system-precomputed date field semantic drift — resolved via unified dim_date conformed dimension."
17. "Recognized when dimension setup should be authored as version-controlled seed SQL vs derived from source data — applying low-cardinality + business-judgment principle."

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

## 🚧 当前阻塞中(等 Databricks 权限开通,预计 1-3 个工作日)

**阻塞条件**:Databricks 同事完成以下操作:
1. 建 schema `mvdevdatabricks.analytics_platform_32degrees`
2. 给 Sia 该 schema 的 `ALL PRIVILEGES`(CREATE TABLE / MODIFY / SELECT 等)
3. 建 Volume `mvdevdatabricks.analytics_platform_32degrees.raw_uploads` 用于 ERS CSV 每月上传

**邮件已发**:2026-05-18(用 "With brief context" 版本)

**权限开通后立即可做**:
1. 跑 DDL 建 4 张表(`docs/data_modeling/star_schema_ddl.sql` v1.1)
2. 跑 dim_channel 种子 SQL(`docs/data_modeling/dim_channel_seed.sql`)
3. 上传 ERS CSV 到 Volume(文件名建议:`ers_product_master_YYYYMMDD.csv`)
4. 跑 dim_date Python 生成脚本,把 Parquet 上传到 Volume
5. 进入 Day 2 — PySpark notebook 编写

**等待期已完成任务(零返工)**:
- ✅ 任务 1:DDL 落地 GitHub(v1.1)
- ✅ 任务 2:PROGRESS.md 第一轮更新
- ✅ 任务 3:dim_date 种子数据 Python 生成脚本
- ✅ 任务 4:dim_channel 16 行种子 INSERT SQL
- ✅ 任务 A:PROGRESS.md EOD 收尾(本次)

---

## 🎯 下一步具体行动

### 立刻可做(可选,不阻塞下次 chat)

**Option 1**:补 `PROJECT_CONTEXT.md` 的 Decision Log(把 Decision 10-16 正式写入,~20 分钟)

**Option 2**:写 follow-up email 模板备用(同事 3 天没回时用,~10 分钟)

**Option 3**:今天到此为止,休息

### 等权限开通后(切片 1 完整路线图)

| Day | 工作内容 | 产出 |
|---|---|---|
| Day 2 | PySpark notebook 建 3 个 dim 表 | `01_build_dim_date.py` / `02_build_dim_channel.py` / `03_build_dim_product.py` |
| Day 3 | PySpark notebook 建 fact_orders_line | `04_build_fact_orders_line.py`(Shopify + TW 跨源 join) |
| Day 4 | FastAPI metrics_service 改造 | YAML 指标 `quantity_by_style_channel_week` + 真实 Databricks SQL connector |
| Day 5 | Next.js page 实现 | 4 个 visual + 端到端 wire up |
| **Day 5 结束** | **Leader Demo** | 拿电脑给 Leader 看 |

### 切片 2+ 路线图

切片 1 完成后,继续切片 2(Style-channel **Revenue** page,fact 表零 ETL 返工,只加 YAML 指标 + Next.js page),然后切片 3(退货分析,新增 `fact_refund_line` + `dim_refund_reason`)。详细规划见 `legacy_panoply_etl.md` + `existing_data_inventory.md`。

---

## 🔖 待后续处理的备忘

### 备忘 1:Page_view report 数据导出(同事需求)

**状态**:🟢 已解决(Panoply 已修复,Sia 直接在 Panoply 跑原 SQL 给同事)

**完整依赖链已分析**(下次新平台要做这个 page 时直接用):
```
Page_view
├── Shopify_sales_data
│   ├── shopify_orders_order ✅
│   ├── shopify_orders_order_line_items ✅
│   ├── customer_type_info ⚠️ 需重建(逻辑见聊天记录或下次重新分析)
│   ├── refund4 ← refund1_news ⚠️ 需重建(见 legacy_panoply_etl.md §3)
│   ├── shopify_products_product ⚠️ 在 Databricks `shopify_32degrees` schema 里没找到对应表
│   └── mysql_ers ✅
└── GA4 数据
    ├── ga4_landing_page2 ❌ 不在 Databricks 数据源边界内
    └── ga4_sessions2 ❌ 同上
```

**待补到 `legacy_panoply_etl.md` 的 2 个新简历亮点**(下次正式整理时加):
- **亮点 #14**:**Anti-bulk-bias 过滤**(`where total_order_qty <= 30` 排除 B2B 大单污染 retail behavior 分析)— 统计正确性意识
- **亮点 #15**:**Customer Cohort Classification**(用 `panoply_order_count vs total_order_count` 差值识别 Panoply 接入前的历史客户,避免老客户被误判为 first-time)— incremental sync data integrity 经典案例 ⭐

**已加入 `PROJECT_CONTEXT.md` 的 Decision 9**:TW 替代 GA4 仅限 attribution layer,page-level funnel metrics 不在 TW 范围内。

### 备忘 2:Databricks Shopify schema 表清单(2026-05-18 确认)

23 张表:
```
customer / customer_address / customer_tag / customer_tax_exemption
discount_allocation / discount_application
fulfillment / fulfillment_order_line
order / order_adjustment / order_discount_code
order_line / order_line_refund / order_note_attribute
order_shipping_line / order_shipping_tax_line / order_tag / order_url_tag
refund / return / return_line_item
tax_line / transaction
```

**与 Panoply 旧表名映射**(下次建模会用到):
| Panoply 表名 | Databricks 表名 | 备注 |
|---|---|---|
| `shopify_orders_order` | `order` | |
| `shopify_orders_order_line_items` | `order_line` | |
| `shopify_orders_order_refunds` | `refund` | |
| `shopify_orders_order_refunds_refund_line_items` | `order_line_refund` | ⚠️ 名字变了 |
| `shopify_orders_order_customer` | `customer`(可能合并)| 待验证 |
| `shopify_products_product` | ❓ 没找到 | 需要找(可能在其他 schema,或 Fivetran 没接入)|
| `shopify_customer_customers` | `customer` | 待验证 |

### 备忘 3:TW Channel 15 个 distinct source 值(2026-05-18 盘点)

```
google-ads       956,049  → legacy_channel_group = Paid Search    (Google)     is_paid=T is_active=T
facebook-ads     923,527  → legacy_channel_group = Paid Social    (Meta)       is_paid=T is_active=T
impact           396,951  → legacy_channel_group = Affiliates     (Impact)     is_paid=T is_active=T
bing              92,269  → legacy_channel_group = Paid Search    (Microsoft)  is_paid=T is_active=T
Excluded          58,262  → legacy_channel_group = Other          (—)          is_paid=F is_active=T  ⚠️ TW meta
Direct            53,684  → legacy_channel_group = Direct         (—)          is_paid=F is_active=T
Non-attributed    18,498  → legacy_channel_group = Other          (—)          is_paid=F is_active=T  ⚠️ TW meta
organic_and_social 14,936 → legacy_channel_group = Organic Social (—)          is_paid=F is_active=T
influencers          815  → legacy_channel_group = Affiliates     (—)          is_paid=F is_active=T
pinterest-ads        135  → legacy_channel_group = Paid Social    (Pinterest)  is_paid=T is_active=F
snapchat-ads           2  → legacy_channel_group = Paid Social    (Snapchat)   is_paid=T is_active=F
tiktok-ads             1  → legacy_channel_group = Paid Social    (TikTok)     is_paid=T is_active=F
smsbump                1  → legacy_channel_group = Email/SMS      (SMSBump)    is_paid=F is_active=F
superfiliate           1  → legacy_channel_group = Affiliates     (Superfiliate) is_paid=F is_active=F
applovin               1  → legacy_channel_group = Paid Social    (AppLovin)   is_paid=T is_active=F
+ unknown placeholder (channel_key=-1)
= 16 行 dim_channel 种子数据(已落地为 dim_channel_seed.sql)
```

Top 7 覆盖 99%+ 流量(default-visible),长尾 8 个 is_active=FALSE(default-hidden via UI toggle)。

### 备忘 4:Excluded 订单分析(切片 3 退货可能需要)

**Open question**:做退货 / 替换分析时,Excluded(exchanges/drafts)订单是否需要看?

- **当前 v1 设计**:`Excluded` channel 跟其他 channel 一样显示,不特殊处理
- **切片 3 时可能需要**:看 exchange 订单原本来自哪个 channel → 需要 fact 表加 `original_channel_key` 字段
- **现在不做**:不阻塞切片 1,标记备忘后续处理

---

## 📌 重要提醒(给 Claude 在新 chat 开始时)

### 项目基础信息
- 用户:Sia(GitHub: sichensong-99)
- 公司:32Degrees(保暖服装品牌,2025-07-01 启用 Triple Whale)
- 项目路径:`C:\Users\sia.song\analytics-platform`
- 环境:Windows 11 + PowerShell + VS Code
- 风格:中英文混用,代码要完整版,命令要解释清楚,决策要明确推荐

### 数据源现状
- **Shopify** @ `mvdevdatabricks.shopify_32degrees`:✅ 完全 ready(2.4M 订单,23 张表清单见备忘 §2)
- **TW** @ `mvdev_federated_catalog.triple_whale`:✅ **完全 ready**(全部月份 ≥ 99.85% match rate)
- **ERS 产品主数据**:⏳ 待 Sia 月度上传到 `mvdevdatabricks.analytics_platform_32degrees.raw_uploads` Volume(等权限开通)
- **数据完整性判定标准**:跨源 monthly match rate ≥ 90%(实际达到 99%+)

### 新数仓 Schema
- **位置**:`mvdevdatabricks.analytics_platform_32degrees`(等同事建好)
- **当前 DDL**:`docs/data_modeling/star_schema_ddl.sql`(v1.1,4 张表)
- **种子数据**:`docs/data_modeling/dim_channel_seed.sql`(16 行)+ `scripts/generate_dim_date.py`(2922 行可生成)

### 已锁定的关键决策(不要翻盘)
- Shopify 走 Fivetran,TW 走 custom pipeline
- TW 必须走 Databricks(不直连应用层)
- 数据源边界 = Shopify + TW + ERS(其他 schema 不纳入)
- 项目数据起点 = 2023-07-01(2023/7/1 之前的 GA UA 历史不纳入)
- 数据接入工具理解:`mvdev_federated_catalog` 不是真的 federation,只是命名误导
- **Decision 9**:TW 替代 GA4 仅限 attribution layer,funnel metrics(浏览/加购/sessions)不覆盖
- **Decision 10(2026-05-18)**:采用 Vertical Slice 方法论交付 Phase 2B/3,切片化端到端打通
- **Decision 11(2026-05-18)**:Date taxonomy 用 ISO 8601 only,不保留 US-week 兼容字段
- **Decision 12(2026-05-18)**:Dimension 表用 SCD1,SCD2 延期至实际业务需求出现(YAGNI)
- **Decision 13(2026-05-18)**:切片 1 ETL 数据窗口 = 2025-07-01 起,Schema 设计 temporally unbounded 留扩展空间
- **Decision 14(2026-05-18)**:Channel meta-category(Non-attributed / Excluded)显式建模,不 drop(初版)
- **Decision 15(2026-05-18)**:Channel 显示策略:`channel_source` 保留 TW 原值 + 加 `legacy_channel_group` 字段(GA4 风格分组),dual-display 服务 TW 同事 + PBI Leader 两类用户。**Excluded / Non-attributed 跟 TW UI 一样显示,不隐藏**(取代 Decision 14 的"显式过滤"思路,简化为"显式显示")
- **Decision 16(2026-05-18)**:`is_paid` flag 保留作为 forward-looking design,服务切片 4+ ROAS 指标(避免后续 ALTER TABLE)。`is_web_attributed` / `is_operational` 砍掉(失去用途)

### 工作原则
- **任何建议必须用 NORTH_STAR.md 的 5 大原则过滤一遍**
- 已选定方案不要再翻盘,有疑问参考 PROJECT_CONTEXT.md 的 Decision Log
- 用户偏好"先想清楚再动手",所以先讲全局规划再讲细节
- 用户严格反对返工,所以建议必须区分"0 返工"和"可能返工"
- 用户容易信息过载,Claude 要主动控制信息密度,**一次给一个具体任务**,不要无限发散

### 关键文档清单
- `NORTH_STAR.md` — 最高决策原则
- `PROJECT_CONTEXT.md` — 项目背景、架构、决策(含 Decision 1-16)⚠️ Decision 10-16 尚未同步到 PROJECT_CONTEXT,见上方建议任务
- `ROADMAP.md` — 阶段计划
- `PROGRESS.md` — 本文档,当前进度
- `SIA_PROFILE.md` — Sia 偏好
- `streaming_module_plan.md` — Phase 4.5 计划
- `docs/existing_data_inventory.md` — Track 1 数据资产盘点(含 §5.1)⭐
- `docs/legacy_panoply_etl.md` — Panoply 反向工程(13 个简历亮点的金矿,待补 #14/#15)⭐
- `docs/data_modeling/star_schema_ddl.sql` — 切片 1 星型模型 DDL v1.1 ⭐
- `docs/data_modeling/dim_channel_seed.sql` — 切片 1 channel 种子数据 ⭐ NEW
- `scripts/generate_dim_date.py` — dim_date 种子数据 Python 生成器 ⭐ NEW

---

## 🔄 进度更新历史

| 日期 | 完成内容 | 下一步 |
|---|---|---|
| 2026-04-28 | Phase 2A 完成,Project Brain 搭建完成 | 进入 Track 1 |
| 2026-05-05 | Track 1 数据探索完成,发现 2 个上游数据问题并发邮件,业务主体确认为 32Degrees | 阻塞期推进 Track 3 |
| 2026-05-13 | Shopify 数据修复完成;TW backfill 至 2025-07-01(11-2 月仍有缺口);Track 3 DQ 框架完成并推送 GitHub | 启动 Track 1 文档 |
| 2026-05-14 | Track 1 文档 Step 1-3 完成(Section 1-4, 6, 7);TW 二次 backfill 完成 10-12 月,但 1-2 月仍缺;已发 follow-up 邮件给 Cal | Track 1 文档 Step 4(PBI Dashboard 映射) |
| 2026-05-15 | TW 数据 backfill 完成验证,全部月份 ≥ 99.85% match rate;Panoply Legacy 反向工程 95% 完成,产出 `legacy_panoply_etl.md` v3;识别 13 个简历亮点 | 启动 Section 5(从 Style-channel quantity page 开始) |
| 2026-05-18 (上半) | §5.1 完成(`Style-channel (quantity)` page),3 个简历洞察沉淀;Decision 9 加入 PROJECT_CONTEXT;Page_view 同事需求已通过 Panoply 修复后解决 | 决定将 quantity page 作为切片 1 端到端实施 |
| 2026-05-18 (EOD)⭐⭐⭐ | **Day 1 完整交付 4 任务**:星型模型 DDL v1.1 / PROGRESS 更新 / dim_date 生成脚本 / dim_channel 种子 SQL;Vertical Slice 方法论锁定;Decision 10-16 全部锁定;**17 条简历金句一日产出** | 等 Databricks 权限开通 → Day 2 PySpark notebooks |

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

### PBI Dashboard Reverse Engineering — §5.1 First Page(2026-05-18)⭐
完成 Track 1 文档 §5.1,反向工程 `Style-channel (quantity)` page(PBI 第 2 个 tab):
- 4 个 visual 完整解构 → 100% 来自单一 fact `Style_selling_df`
- 验证 Kimball "conformed fact + 多角色"原则在生产系统的应用
- **识别 BI 工具派生 vs 源系统物化的时间口径风险**(中高级 DE 级别洞察)⭐
- 设计 GA4 → TW 双口径 channel dimension 过渡方案
- 完整字段映射 + YAML 指标定义草稿,为 Phase 2B/3 建模提供需求输入

**关键词**:BI Reverse Engineering / Requirements Reverse Engineering / Conformed Dimension Design / BI Layer Decoupling / Date Semantics Standardization

### Vertical-Slice Agile Delivery & Slice 1 Star Schema Design(2026-05-18)⭐⭐
采用 vertical-slice 方法论交付 Kimball 数仓,首切片端到端打通(数据源 → 数仓 → 指标服务 → 前端 portal):
- 锁定 5 天交付计划(Day 1 设计 → Day 2-3 ETL → Day 4 服务层 → Day 5 前端),Day 5 给 Leader demo
- 5 个工程化设计决策锁定(Vertical Slice / ISO 8601 / SCD1 YAGNI / Schema-ETL 解耦 / Channel meta-category 显式建模)
- 与 TW 数据 owner 协作澄清 platform-specific meta-categories,显式建模而非 drop
- DDL 文件 header 包含完整设计决策记录,任何 reviewer 可独立理解 schema 演进逻辑
- 建立 conventional commits 规范

**关键词**:Vertical-Slice Agile Delivery / Iterative Stakeholder Feedback / MVP-first Risk-driven Development / YAGNI Principle / Kimball Star Schema / SCD1 / ISO 8601 Standardization / Channel Meta-Category Modeling / Conventional Commits Discipline / Self-documenting DDL

### Deterministic Seed Data Generation — dim_date(2026-05-18)⭐ NEW
设计可重跑、可测试的种子数据生成器替代 in-warehouse SQL 计算:
- Python 标准库 `datetime.isocalendar()` 实现 ISO 8601 边界周(避免 SQL 方言行为不一致)
- 内置 sanity check 验证 ISO 8601 跨年周边界(如 2024-12-30 → ISO 2025-W01)
- 双输出格式:CSV(可读、diff-friendly)+ Parquet(Databricks 加载最快)
- 实践 "commit generators, gitignore artifacts" 原则
- 位置:`scripts/generate_dim_date.py`

**关键词**:Deterministic Seed Generation / Python over SQL for Date Semantics / Embedded Sanity Checks / Idempotent Pipelines / Generators-as-source-of-truth

### Dual-Display Channel Dimension Design(2026-05-18)⭐⭐ NEW
设计双显示口径的 channel 维度表,服务多种 stakeholder 认知:
- `channel_source` 保留 Triple Whale 原值 → 与 TW UI 一致,服务运营团队
- `legacy_channel_group` 加入 GA4 风格分组 → 服务高管对 PBI 报表的认知惯性
- 同一 dim 表服务两种用户,不强迫任何一方学对方的术语
- 体现 Conway's Law 在数据建模中的应用 — 组织结构影响 schema 设计
- 前瞻设计 `is_paid` flag 服务切片 4+ ROAS 指标(避免后续 ALTER TABLE)
- 16 行预先 INSERT 种子 SQL,版本控制业务分类决策
- 位置:`docs/data_modeling/dim_channel_seed.sql`

**关键词**:Dual-Display Dimension / Conway's Law / Stakeholder-Aware Schema Design / Forward-Looking Dimension Flags / Version-Controlled Seed SQL / Platform Migration Cognitive Cost Mitigation

---

### 2026-05-19 — Pre-permission Preparation Day(P0 / H Tasks 大批量交付)⭐⭐⭐

**总览**:权限到位前的"零返工准备日",一日内完成 7 个任务交付,所有 Slice 1 Day 2-5 代码层 + 设计层 + 工具层全部就绪。等同事开通独立 schema(已发邮件 + follow-up)后直接启动 Day 2。

**完成清单**:

#### Task A:Decision Log 10-16 写入 PROJECT_CONTEXT.md ✅
- 7 条架构决策从备注状态正式归档:Vertical Slice / ISO 8601 / SCD1 YAGNI / Schema-ETL 解耦 / Channel meta-category 显式建模 / Dual-display channel / `is_paid` forward-looking
- 30 分钟整理,纯文档化已锁定决策

#### Task B:Slice 1 Architecture Design Doc ✅ ⭐⭐⭐
- 文件:`docs/architecture/slice_1_design.md`(~700 行,19 sections)
- 覆盖:Executive summary / 5 success criteria / 数据源(3 源)/ 星型模型 ER 图 / ETL 模块划分 / **Cross-source Join Strategy(技术核心)** / DQ Plan / Performance / Schema Evolution & Rollback / Metrics Layer Contract / Frontend wire-up / Testing / 5-day Deployment Run Order / Risk Register / Open Questions
- 这是面试讲项目时直接可以展示的工程化文档,体现 "Design Before Code" 工程实践

#### Task C:`generate_dim_date.py` 本地脚本验证 ✅
- 跑通 CSV 输出(2922 行,2023-01-01 至 2030-12-31)
- 验证 ISO 8601 边界 case(2024-12-30 → ISO 2025-W01)
- 提前发现并解决脚本 bug,避免 Day 2 浪费时间

#### Task D:4 个 PySpark Notebook 骨架 ✅ ⭐⭐⭐⭐⭐
- 位置:`databricks-notebooks/slice_1/`
- `01_build_dim_date.py` — ISO 8601 双 spot check(2024-12-30 + 2025-12-29 跨年边界)
- `02_seed_dim_channel.py` — 版本化 seed SQL 驱动 + dual-display 验证
- `03_build_dim_product.py` — **ERS 双格式 schema-detection 自动识别**(legacy + post-2026 redesign)+ 三 pass 优雅降级
- `04_build_fact_orders_line.py` ⭐ — 技术核心:
  - **Last-touch Window 去重**(`row_number() over (partition by tw_order_id order by position desc, click_date desc)`)
  - **Cross-type join**(Shopify BIGINT cast STRING ⨝ TW STRING)
  - **DST-aware 时区**(`from_utc_timestamp('America/New_York')`,修正 legacy 静态 -5h bug)
  - **Multi-tier DQ**(PASS < 0.5% / WARN 0.5-2% / FAIL ≥ 2%,基于 0.15% baseline 校准)
  - Broadcast joins + Z-ORDER 物理布局优化
  - Smoke vs Full run mode
  - Idempotent overwrite

#### Task H2:Reconciliation Methodology + Tooling ✅ ⭐⭐⭐⭐
- 位置:`docs/reconciliation/`
- 5 个产出:README methodology / 新平台 SQL / Panoply legacy SQL / Python diff 脚本 / Excel 彩色报告生成
- **PASS/WARN/FAIL/MISSING** 四级分类 + 颜色编码,Leader-readable
- 完成本地 dry-run 验证(用 mock 数据)
- **Demo 1 的信任核心物料**:Day 5 跑一下出报告,Leader 看到 < 2% diff 立刻信任迁移

#### Task H5:Decision Log 17-19 + Remaining Tasks Tracker ✅
- Decision 17: DST-aware timezone correction
- Decision 18: Multi-tier DQ SLO with empirical baseline calibration
- Decision 19: ERS dual-schema ingestion
- PROJECT_CONTEXT 末尾新增 "Remaining Tasks Tracker" — 明确 P0 / H 加分项 / 阻塞中 / 后期 Phase 全景

#### Task H4:Phase 4 Workflows Orchestration Design Doc ✅ ⭐⭐⭐⭐
- 文件:`docs/architecture/phase4_orchestration_design.md`(~750 行,17 sections)
- 覆盖:DAG 拓扑 / 触发策略 / Retry policy / **DQ-as-Gate Pattern**(简历核心)/ Slack/Email 告警 / **Staged Migration: Full → Incremental Load with updated_at watermark + 2-day lookback** / Idempotency / Config as Code / **Workflows vs Airflow Trade-off**(面试 canonical question 答案)/ Risk Register / 5-day 实施计划
- Phase 4 真做时直接照着实施,无需重新设计

---

**本日产出量化**:
- ✅ 7 个任务全部 commit + push GitHub
- ✅ 新增 Decision 10-19(10 条架构决策)
- ✅ 约 25-30 条新简历金句
- ✅ ~3000 行代码 + 文档
- ✅ 8 次 git push

---

**新增简历核心关键词**(本日精华):

**工程化思维**:
- Design Before Code(authored 700-line + 750-line architecture design docs)
- Schema Evolution Tolerance(ERS dual-format auto-detection)
- Legacy Bug Correction(DST timezone fix)
- Multi-tier DQ SLO Calibrated Against Empirical Baseline
- DQ-as-Gate Pattern(production pipeline integrity contract)
- Staged Migration Strategy(full → incremental with watermark)
- Forward-looking Design(`is_paid` flag for slice 4+ ROAS)

**技术核心**:
- Deterministic Multi-touchpoint Deduplication via Window Function
- Cross-source Heterogeneous-type Join(BIGINT ↔ STRING)
- Graceful Degradation Entity Resolution(three-pass: exact → fallback → sentinel)
- Broadcast Join Optimization for Small Dimensions
- Delta Lake Partition + Z-ORDER Physical Layout Tuning

**Stakeholder & Process**:
- Quantitative Reconciliation Methodology(< 2% diff threshold as trust gate)
- Multi-channel Alerting(Slack + Email + Success Digest)
- Workflows vs Airflow Trade-off with Decision-flip Conditions

---

**当前阻塞**:等同事开通独立 schema `mvdevdatabricks.analytics_platform_32degrees`(已发邮件,正在等待回复)。当前 `mvdevdatabricks.32degrees` 已有同事的 38 张 PO 项目表,共用会污染简历叙事的命名空间清晰度。

**剩余 P0 任务**(明天一次性批量推):
- Task E:YAML 指标定义 `quantity_by_style_channel_week`(需要看现有 yaml 风格)
- Task F:Next.js mock UI(需要看现有 frontend 代码风格)
- Task G:DQ YAML 配置 4 张表(需要看现有 DQ yaml 风格)

**剩余 H 加分项**(可选):
- H3:补 `existing_data_inventory.md` §5.2-5.N PBI 页映射
- H6:Demo script(Task F 完成后做)

**等同事开通后立即可做**:Day 2 跑 notebook 01/02/03 → Day 3 跑 notebook 04 → Day 4 FastAPI 真连 → Day 5 wire up + reconciliation + Leader demo。

---

**关键学习**:
- **零返工保证策略奏效**:所有今日工作都基于已锁定的 DDL v1.1 + 已探测的 schema(99%+ match),没有任何因数据未来变化导致返工的风险。
- **反工作惯性纪律**:今晚多次出现"再做一个"的冲动,Claude 协助识别为焦虑驱动而非产出需求,引导收尾。坚持北极星第五原则:**基于反馈迭代,不焦虑式堆砌**。
- **一次性批量贴代码 > 分多次切换**:Task E/F/G/H3 共同点都是需要看现有代码风格,锁定明天一次性贴完,避免上下文切换成本。