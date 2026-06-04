# PROGRESS.md — 项目进度

> **阅读顺序**:本文件按时间倒序,最新在最上。
> 顶部「当前状态速览」始终保持最新;往下是历史日志(含简历素材沉淀,全部保留)。
> 凡标 `⚠️【历史】` 的段落是过时/被推翻的旧版本,保留作演进记录,**判断现状以速览区为准**。

---
# ═══════ 当前状态速览（更新于 2026-06-04）═══════

## Phase 6 部署 / 真数据上线

* **6.5 ✅ 完成**：real data 已在部署后的 Azure Container Apps stack 中上线

  * M2M service principal 已端到端跑通 ✅
  * Dashboard 已显示真实数据 / real numbers ✅
  * Phase 6.5 状态：**real data LIVE in deployed ACA stack** ✅

## Phase 4.5 Streaming

* **Phase 4.5 ✅ code-complete + running**

  * Streaming pipeline 已完成并运行中 ✅
  * P1 hardening 已完成：

    * dedup 已加 ✅
    * exactly-once / checkpoint recovery 已验证 ✅
  * 已支持 **流批一体**：

    * 通过 `RUN_MODE` 参数切换执行模式 ✅
    * `stream` = 持续实时跑
    * `backfill` = 处理现存数据后停止
  * 当前状态：**code-complete + running + P1 verified + RUN_MODE supported** ✅

## Phase 5 Platformization

* **Phase 5 ✅ code-complete**

  * Catalog 已完成 ✅
  * Lineage 已完成 ✅
  * mock 模式下 Catalog + Lineage 验证 OK ✅
  * Redis benchmark vs real query：pending

## Cost / ROI

* **Cost / ROI report ✅ done**

  * 成本 / ROI 报告已完成 ✅

## Open / Pending

* **Cal backfill → re-reconcile**

  * 当前差异：`−1.51%`
  * 目标重新 reconcile 后预计：`~−1.7%`

* **New-stack cost**

  * 需要基于 representative month 重新计算新 stack 成本

* **Chaos-generator swap**

  * 待完成

* **Redis benchmark vs real query**

  * 待完成
  * Phase 5 中 Redis benchmark 仍需对真实查询表现做对比

* **Report-filtering → Slice 2**

  * 待推进到 Slice 2

* **Leader demo + README + blog**

  * 待准备 leader demo
  * 待完善 README
  * 待写 blog

# ═══════ 当前状态速览（更新于 2026-06-03）═══════

## Phase 6 部署
- **6.4 ✅ 完成**：两个 Container App 上线（ACA / RG 32D-ecom-rg / eastus2）
  - frontend：external ingress, **min=0**, port 3000
  - metrics-service：internal ingress, **min=1**(为修冷启动改的), port 8000
  - 镜像 `az acr build` 云端构建；passwordless 用 user-assigned identity `ap32d-aca-identity`（AcrPull + KV Secrets User）
  - secret 走 Key Vault 引用（`ap32d-kv`）：jwt-secret ✅；databricks-client-id / -secret = 占位待真值
  - **mock 模式端到端跑通 = 可演示的成品** ✅
- **6.5 真数据（M2M）= 卡外部，未完成**
  - 后端 env 已配好（databricks / oauth-m2m / 真 hostname+path / client 凭据 secretref），但**当前临时切回 mock 让它能跑**
  - 镜像已就绪：`metrics-service:v2`（含 `databricks-sdk` + oauth-m2m 分支）
  - **等 Lee（account admin）两样**：① 生成 SP `32_degrees` 的 OAuth secret → client_id + secret；② 给 SP 数据权限（CAN USE warehouse + SELECT analytics_platform_32degrees）。已回复 Lee。
  - 我**不是** account admin（进不去 SP 管理页）；正确 account console = `accounts.cloud.databricks.com`（不是 azuredatabricks.net）
  - **凭据+权限到位后照这几条切（PARKED）**：
```powershell
    az keyvault secret set --vault-name ap32d-kv --name databricks-client-id --value "<Lee给的>" -o none
    az keyvault secret set --vault-name ap32d-kv --name databricks-client-secret --value "<Lee给的>" -o none
    az containerapp update -n metrics-service -g 32D-ecom-rg --set-env-vars "METRICS_DATA_SOURCE=databricks" --revision-suffix m2mlive
    az containerapp logs show -n metrics-service -g 32D-ecom-rg --tail 100
```

## 数据侧
- **DQ 残留已修**：DQ-as-Gate 在 06:30 定时跑里拦下 1 个 null product_key（fail-closed）。根因=旧版（加 coalesce 前）跑留下的残留行（updated_at 2025-05-28，落在每日增量窗口外，故增量永不重碰）。**notebook 04 本身无 bug**（coalesce 正确）。hotfix：`UPDATE ... SET product_key=0 WHERE product_key IS NULL`（Unknown member key=0 已存在）。
- **dpsync 框架（Cal 新建，替代 Fivetran）**：`dpsync.shopify_32degrees.order_metafield` 有 replace_refund 列 → **是宽表，不是 Fivetran EAV(key/value/owner_id)**。值分布：Replace 224 / Refund 266 / Gift Card 52 / null 139。**replacement 信号 = replace_refund=='Replace'**。
  - notebook 04 §3b 已适配宽表（指向 dpsync 表）。
  - **等 Cal backfill 2025-07-01+** → 再 full refresh + 重新对账（预期 −1.51% → ~−1.7%）。已邮件请 Cal backfill。

## 关键基础设施 ID（别再重新发现）
- ACR `analyticsplatform32dacr.azurecr.io`｜ACA env `analytics-platform-env`（domain `redhill-e43933ed.eastus2.azurecontainerapps.io`）｜KV `ap32d-kv`｜RG `32D-ecom-rg`/eastus2｜sub `bef25ab0-...`｜identity `ap32d-aca-identity`
- 后端 internal FQDN：`metrics-service.internal.redhill-e43933ed.eastus2.azurecontainerapps.io`
- 前端公网：`https://analytics-frontend.redhill-e43933ed.eastus2.azurecontainerapps.io`
- 镜像：`analytics-frontend:v1`｜`metrics-service:v2`
- Databricks workspace host `dbc-620cc0fc-b4ee.cloud.databricks.com`｜warehouse http_path `/sql/1.0/warehouses/39f94dd6ed9a78a4`

## 人
- **Lee Tepper**（lee.tepper@wpmv.com）：建了 SP `32_degrees`、account admin、管 SP 凭据 + 数据权限
- **Cal Peyser**：建 dpsync 框架、也有 account console 访问

## 下一步（新 chat 开局）
1. 等 Lee 给 SP secret + 数据权限 → 跑 PARKED 命令切真数据 → 看真 dashboard
2. 等 Cal backfill → full refresh + 重新对账（replacement）
3. 真数据通后 Phase 6 收尾：成本报告、文档、blog、README、简历定稿

# ═══════ 当前状态速览(2026-06-02)═══════
## 🚦 两条线 + 平台栈状态
| 线 | 状态 |
|---|---|
| Slice 1(Style × Channel quantity)| ✅ 过 trust gate(−1.51%,残差全归因),数据可信可用,team 可访问。**已上线每日调度**。replacement 精度待 metafield 异步重跑(不阻塞)|
| Amazon ingestion | ✅ 全部完成(826 行,D25 completeness、D26 范围裁剪,冒烟测过,completion summary 已入库)|
| **Phase 4 编排** | ✅ **全部完成** —— 7-task DAG 上线、DQ-as-Gate(Spark)、fault injection 验证、增量 MERGE(待 C/D/E 对账确认)、runbook |
| **Phase 6 部署** | 🔄 进行中 —— 容器化✅、Terraform 地基待跑(6.3)、IT 给 SP 待回 |
| Slice 2(Revenue page)| 📋 Slice 1 demo 后启动 |
| page_view report | 📋 等 TW Web Analytics 接入(邮件已发)|

## 📐 现行模型 = Decision 22 v3(不变)
- `is_sales_attributable = NOT(is_exc_order OR is_replacement_order)`;refund 走行级净扣 `refunded_quantity`(全 restock_type 含 cancel);净销量 = quantity − refunded_quantity
- replacement 信号 = Shopify `order_metafield` 表,notebook 04 已做表存在性自动检测 + 优雅降级

## 🔢 fact 加载 = Decision 28(新,增量)
- 全量改增量:watermark = Shopify `order.updated_at`(退款/改单会 bump,捕获晚到退款)+ 2 天 lookback;Delta MERGE upsert(key=`shopify_line_id`),非分区覆盖(退款回填老 iso_week)
- `FULL_REFRESH` 开关切全量/增量(backfill);水位线表 `pipeline_watermark`
- ⏳ **明天待办**:Step C 全量建基线 → D 切增量 → E 对账(`row_count==distinct_lines` 验证无重复)

## 🔓 Open follow-ups
**明天必做(增量验证)**:
- [ ] notebook 04 增量版:全量建基线 → 增量跑 → 对账(C/D/E),通过后写 Decision 28 + 更新简历 §9 数字
**Phase 6(等外部)**:
- [ ] 6.3 Terraform apply(ACR/KeyVault/Log Analytics/Container Apps env)— 明天跑
- [ ] IT 注册 Databricks service principal(连数据用,PAT 禁、U2M 无浏览器)— 邮件已发,等回
- [ ] leader email 已发 IT 开 resource group ✅(`32D-ecom-rg`,eastus2,我 Owner)
**Slice 1**:
- [ ] 重跑 notebook 04 激活 `is_replacement_order`（metafield 到位后）→ 重新对账
- [ ] Leader demo(script:`docs/demo/leader_demo_script.md`)

## 🗂️ 已建表
**Slice 1 四表**:dim_date 2,922 / dim_channel 23 / dim_product 36,828 / fact_orders_line ~9.97M（+ 新列 `order_updated_at`，增量水位线源）
**新增**:`pipeline_watermark`（增量状态）/ `pipeline_run_history`（success digest 行数历史）
**Amazon 三层**:amazon_silver_shipment_item 826 / amazon_silver_shipment 21 / amazon_gold_receiving_by_sku 826

## 🛠️ 编排 / 部署资产（新）
- Workflows job `slice_1_daily`（7-task,每日 06:30 ET,Personal Compute,Decision 27）+ `amazon_shipment_ingestion_weekly`
- job JSON config-as-code:`databricks-workflows/`;DQ configs:workspace `slice_1/dq_configs/` + repo `metrics-service/data_quality/configs/`(两处同步)
- 容器化:`frontend/Dockerfile`(standalone)+ `metrics-service/Dockerfile`(uv)+ 根 `docker-compose.yml`
- IaC:`infra/`(Terraform — ACR/KeyVault/Log Analytics/Container Apps env,RG `32D-ecom-rg`/eastus2)
- runbook:`docs/RUNBOOK.md`

## 🔧 环境 cheat sheet
- 项目根 `C:\Users\sia.song\analytics-platform` | GitHub sichensong-99/analytics-platform
- Databricks catalog `mvdevdatabricks`,主 schema `analytics_platform_32degrees`
- Shopify `shopify_32degrees` | TW `mvdev_federated_catalog.triple_whale` | ERS raw `mvdevdatabricks.32degrees.raw_uploads/ers/`
- metrics-service:OAuth U2M(`.env` DATABRICKS_AUTH_TYPE=oauth,无 PAT)| 起后端 `cd metrics-service; uv run uvicorn app.main:app --reload`
- Databricks CLI:`databricks jobs create/delete/list`(OAuth U2M 登录)
- Azure CLI:`az login`(公司租户)| Terraform 在 `infra/`:`terraform init/plan/apply`
- compute:Slice 1 notebook 用 classic(需 cache);Amazon 用 Serverless
- 简历金句单一正源:`docs/RESUME_HIGHLIGHTS.md`(已加 §9)
- Decision Log:`PROJECT_CONTEXT.md`(最新 D28 增量;D27 compute 选型)

# ═══════ 当前状态速览(2026-06-01)═══════
- Phase 4 ✅ 全部完成(slice_1 每日调度上线 + runbook + Decision 27);Step 5(fact 增量)parked 待补;进入 Phase 6,6.1 工具链 + Azure 访问验证中。

- Phase 4 Step 1-2 ✅:Amazon job 已 config-as-code 入库;slice_1_daily 7-task DAG 手动跑通;DQ-as-Gate 已 Spark 化,首跑捕获并修复 fact null product_key(新增 dim_product Unknown member key=0 + fact coalesce,Kimball 一致化)。下一步 Step 3(fault injection + Slack)。
## 🚦 两条线状态
| 线 | 状态 |
|---|---|
| Slice 1(Style × Channel quantity)| ✅ 过 trust gate(−1.51%,残差全归因),数据可信可用,team 可访问。replacement 精度待 metafield 异步重跑(不阻塞)。可进 Phase 4 |
| Amazon ingestion | ✅ 数据层全量正确稳定(826 行活跃 shipment 全量,completeness 修复 D25,范围裁剪 D26)。冒烟测 826 通过。剩:completion summary |
| Slice 2(Revenue page)| 📋 Slice 1 demo 后启动 |
| page_view report | 📋 等 TW Web Analytics 接入(邮件已发)|

## 📐 现行模型 = Decision 22 v3(唯一有效,早期版本已作废)
- `is_sales_attributable = NOT(is_exc_order OR is_replacement_order)` —— 仅整单排除 EXC + replacement
- refund 走行级净扣:`refunded_quantity` = SUM(order_line_refund.quantity),覆盖全 restock_type(含 cancel);净销量 = quantity − refunded_quantity
- cancel 不单独建订单级 flag(Shopify 给取消单生成的 restock_type='cancel' refund line 天然在行级净扣内)
- `is_refunded` / `is_refund_order` 已删
- replacement 信号 = Shopify `order_metafield` 表(独立表 owner_id/key/value,key='replace_refund' value='["Replace"]'),notebook 04 已做表存在性自动检测 + 优雅降级

## 🔓 Open follow-ups(全部等权限恢复,除标注外)
**Slice 1**:
- [ ] `DESCRIBE order_metafield` + sample 确认 owner_id/key/value schema
- [ ] 重跑 notebook 04 激活 `is_replacement_order` → 重新对账(预期 −1.51% → ~−1.7%)
- [ ] Leader demo(script:`docs/demo/leader_demo_script.md`)

**Amazon**(数据层全部完成,仅剩收口文档):
- [x] 重跑 01→02→03 + 验证 1-5 ✅(826 行全量,join 自洽,created_date unparsed=0,gap 公式抽查全对)
- [x] 真连冒烟测 `/snapshot/amazon_fba_receiving_by_sku` ✅ 826 行
- [x] mock + 真连前端页面验证 ✅
- [x] Amazon completion summary(下一步:Claude 起草)

**不依赖权限、随时可做**:Amazon 前端 mock 验证 / Slice 2 revenue 预研究 / Slice 1 completion summary 收尾 / 文档整理

## 🗂️ 已建表
**Slice 1 四表**:dim_date 2,922 / dim_channel(v2.0)23 / dim_product 36,680 / fact_orders_line 9,965,352
**Amazon 三层**:amazon_silver_shipment_item 826 / amazon_silver_shipment 21 / amazon_gold_receiving_by_sku 826

## 🔧 环境 cheat sheet
- 项目根 `C:\Users\sia.song\analytics-platform` | GitHub sichensong-99/analytics-platform
- Databricks catalog `mvdevdatabricks`,主 schema `analytics_platform_32degrees`
- Shopify `shopify_32degrees` | TW `mvdev_federated_catalog.triple_whale` | ERS raw `mvdevdatabricks.32degrees.raw_uploads/ers/`
- Amazon Secrets:Databricks scope `amazon`(lwa_client_id/secret/refresh_token/seller_id)
- metrics-service:OAuth U2M(`.env` DATABRICKS_AUTH_TYPE=oauth,无 PAT)
- 起后端:`cd metrics-service; uv run uvicorn app.main:app --reload`
- mock 模式:`$env:METRICS_DATA_SOURCE="mock"` 再起(当前窗口生效)
- 测试 token:`uv run python gen_test_token.py` | 起前端:`cd frontend; npm run dev`
- 简历金句单一正源:`docs/RESUME_HIGHLIGHTS.md`
- compute:Slice 1 notebook 用 classic(需 cache);Amazon notebook 用 Serverless(无 cache)

---

# ═══════ 历史日志(倒序;简历素材全部保留)═══════

## 2026-05-28 — Amazon ingestion 基本完成 + Databricks 权限阻塞

**🚫 当前阻塞(最高优先)**:Databricks 账号 entitlement 被撤
- 工作中突然被登出,重登显示 "no permission to access workspace 2523255732481272"
- metrics-service 连 SQL Warehouse 报 "This API is disabled for users without databricks-sql-access or workspace-consume entitlements"
- 已发邮件给 Databricks 管理员请求恢复 Workspace access + Databricks SQL access
- 这跟代码无关,纯权限事故。恢复前所有连 Databricks 的操作都会失败。

**Amazon shipment ingestion(新增任务,Leader 要求)— 90% 完成**:
- 背景:把 Panoply 上的 Amazon FBA 入库数据迁到新平台,每周一 6am ET 更新,给 planning 同事看。Amazon 与 Shopify/TW 无 join key,独立 domain。
- 架构:放 analytics_platform_32degrees(主 schema)用 amazon_ 前缀隔离(Decision 23);Medallion Bronze/Silver/Gold(Decision 24)。
- 对应 Panoply 两个 connector:
    * connector 1 amazon_shipment_items → notebook 01 → amazon_silver_shipment_item ✅ (212 行)
    * connector 2 amazon_shipments → notebook 02 → amazon_silver_shipment ✅ (4 行)
    * query model amazon_ship → notebook 03 → amazon_gold_receiving_by_sku ✅ (212 行)
- notebook 03 复刻了 Panoply amazon_ship 的 created_date 解析(5 种 shipment_name 格式),unparsed=0%。
- SP-API:LWA refresh token 认证 + 指数退避重试 + 分页 + Silver MERGE 幂等(8 天窗口含 1 天重叠)。凭据存 Databricks Secrets scope=amazon。(⚠️ 早期误把 refresh_token/client_secret 贴进聊天,已 rotate。)
- 后端:main.py 加 /snapshot/{metric_id} 端点(无 date,区别于 /metrics 时间序列);definitions.yaml 加 amazon_fba_receiving_by_sku 指标;databricks_client.py 的 LIST_GUARD_PARAMS 加 statuses/fcs + Amazon mock 分支。
- 前端:dashboards/amazon-shipments/page.tsx(表格+KPI+status/FC filter+CSV export);api/snapshot/[metricId]/route.ts proxy;dashboards 列表页加 Amazon 卡片。
- 调度:Databricks Job 建好(三 task:01∥02 并行 → 03,周一 6am ET,Serverless compute)。
- compute 决策:Amazon 三 notebook 用 Serverless(无 cache,数据小);Slice 1 notebook 04 仍用 classic(需 cache)。

**Amazon 待办(全部等权限恢复)**:
- [ ] 重跑 01→02→03 确认三表是终版产出
- [ ] 验证 1-5:行数自洽 / created_date 全解析 / receiving_gap 正确 / 跟 Panoply 抽查对账
- [ ] 真连冒烟测 /snapshot/amazon_fba_receiving_by_sku(预期 212 行)
- [x] mock 模式本地验证前端页面 ✅ 2026-05-29(前端→Next.js proxy→FastAPI 链路 200/200,dual-mode 在权限断线期独立供数已验证)
- [ ] Amazon completion summary 一节(并进 slice_1_completion_summary 或单独文档)

**验证 5(Panoply 对账)归因**:抽查 FBA19CRBL6RZ,新平台 20 SKU 全到、received 为到仓终值;
Panoply 同 shipment 20 行但 received 全 0、status=IN_TRANSIT,系 5/18 冻结的在途快照。
差异 100% 归因于 Panoply 数据冻结 + 在途状态,非管线缺陷。新平台数据更完整且更新。已知差异,非 bug。

**Slice 1 待办(也等权限恢复)**:
- [ ] order_metafield 表到位后跑 3 个 DESCRIBE/sample SQL → 确认 schema → 重跑 notebook 04 激活 is_replacement_order → 重新对账(预期 −1.51% → ~−1.7%)
- [ ] Leader demo(script 已草拟 docs/demo/leader_demo_script.md)

**Amazon doc 状态**:
- ✅ docs/architecture/amazon_ingestion_design.md(已 push)
- ✅ PROJECT_CONTEXT Decision 23-24(已加)
- ✅ star_schema_ddl.sql 补 amazon_gold 表 DDL
- ⬜ Amazon completion summary 一节(待 dashboard 端到端验证后写)

---

## 2026-05-27 — Slice 1 收尾,对账通过 trust gate

**对账结果**:
- Overall −1.51%(180,670 / 183,438),< 2% trust gate ✓
- 残差完全归因(week 28,基准 D3 验证):EXC 整单 −2,209 + refund 行级 −6,573 + cancel 行级 −803,与新平台减项 7,376 ≈ Panoply 减项 6,705 + 670 偏差完美对上
- 45 个 vend_id 桶 FAIL 不阻塞:小分母放大 + replacement 未排除,trust gate 重定义为"overall < 2% 且残差完全归因"已达成

**Decision 22 v3 锁定**:
- is_sales_attributable = NOT(is_exc_order OR is_replacement_order),只管 EXC + replacement 两类整单排除
- refunded_quantity 行级列 = SUM(order_line_refund.quantity) 覆盖全 restock_type(return / no_restock / cancel / legacy_restock),净销量 = quantity − refunded_quantity
- cancel 走行级 netting 不单独建订单级 flag —— Shopify 给取消单生成的 refund line(restock_type='cancel')天然在行级净扣覆盖范围内
- is_refunded / is_refund_order 已删

**Panoply 真口径(读源码定论)**:
- refund 排除是订单级整单打标剔除(tag 路径 + metafield 路径)
- 销售链路从未 join refund line items → cancel 无单独处理,被当销量
- 全订单状态收入(无 financial_status / cancelled_at 过滤)
- 这解释了 Panoply 与新平台 −1.51% 的方法论差(非误差)

**Panoply 旧报表的精度缺陷(新平台主动修正)**:
- legacy refund 只通过 tag 反推,覆盖率 ~22%(原生 175,409 单 vs tag 39,382 单)→ 新平台用原生 order_line_refund 全覆盖
- legacy 不识别 cancel → 取消单的 803 件被当销量
- 类比 Decision 17 DST bug 修正,文档化为 intentional correction,不追 0% diff

**metafield 状态**:
- Databricks 同事昨天刚 enabled `order_metafield` table,几小时内可见 → metafield 是独立表(owner_id/key/value 行级),不是 order 表的列(Fivetran 标准 Shopify connector 结构)
- notebook 04 Section 3b 已改为表存在性自动检测,优雅降级
- metafield 到位后流程:DESCRIBE order_metafield → 核 schema → 重跑 notebook 04 → 重新对账(预期 overall 残差略往下 ~1.6-1.8%)

**本日交付物**:
- ✅ notebook 04 v3(Section 3b/3c/7/8 + header)— 行级 refund netting + replacement 优雅降级
- ✅ 01_new_platform_query.sql v3(SUM(quantity − refunded_quantity) + is_sales_attributable filter)
- ✅ 02_panoply_legacy_query.sql v3(BigQuery EXTRACT 语法,Sia 自修)
- ✅ definitions.yaml quantity_by_style_channel_week v1.2(breaking change)
- ✅ star_schema_ddl.sql v2.0(dim_channel 重复定义清理 + 三表同步实际 schema + fact 改为 Decision 22 v3)
- ✅ run_reconciliation.py 跑通:180,670 vs 183,438 = −1.51% PASS

**待办**:
- ⏳ metafield 到位 → 重跑 notebook 04 → 重新对账
- ⏳ Demo(H6 demo script,已开始草稿)
- ⏳ next page: page_view(需 TW Web Analytics 接入,邮件已发)

### Slice 1 量化基线(2026-05-27 freeze)
> 这些数字是 Slice 1 demo 的核心证据,简历 STAR 里的 R(Result)。metafield 落地重跑后会更新,但 baseline 保留作演进对比。

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

> ⚠️【历史·已被 D3 验证更新】下面"核心结论"是 2026-05-26 破案前的笔记 —— 当时写"偏差 −2,768 / cancel 算不算需看源码确认"。最终结论(见本日开头):残差 −2,880,逐项 = EXC 2,209 + refund 6,573 + cancel 803,cancel 确定走行级净扣。保留作演进记录。

**核心结论**:
- is_sales_attributable = NOT(is_exc_order OR is_replacement_order),仅管整单排除两类。
- refund 改为行级净扣减:新增 refunded_quantity 列,净销量 = quantity − refunded_quantity。is_refund_order 列废弃(整单排除 refund 经对账证伪:残差 1.97%→6.57%)。
- 对账(iso_week 28,Panoply 基准 183,438):行级净扣减 = 180,670(−1.51%),方向正确。
- 偏差 −2,768 已定位:order_line_refund 含 cancel 类(restock_type),旧报表对 cancel 无单独处理 → cancel 算不算需看 Panoply 源码确认。

**下一步(新 chat)**:发 Style_selling_dfNEW 全嵌套 + refund1_news + refund4 + 02_panoply_legacy_query.sql → 确定 Panoply 真实口径 → notebook 04 / 对账 SQL / DDL 三个终版。

**并行待办**:
- Fivetran 同事:order metafield 同步(replacement 识别);同事提示字段可能在 returns 表,待查。
- Databricks 同事:TW Web Analytics 表接入(page_view funnel)— 邮件已发。
- star_schema_ddl.sql 待修(dim_channel 重复定义 + fact 段过时)。
- Demo 未做。

> ⚠️【历史】下面这段是 v3 定稿前的待办笔记。v3 已完成,最终模型见本文件顶部速览区。保留作演进记录。

**Decision 22 需改 v3**:模型从"三类合一 boolean"改为"EXC+replacement 用 boolean,refund 用行级 refunded_quantity 列"。

**三类排除信号已查清(replacement / refund / EXC)**:
- EXC 换货单:`order.name LIKE '%EXC%'` — Databricks 原生可识别(窗口内 53,467 单)
- refund 退款单:Shopify 原生 `refund` 父表 join order_id(窗口内 175,409 单)。取代 Panoply 的 `tags LIKE '%refund%'` 反推 —— Panoply 同口径仅 39,382 单,证明原生表更全(系统自动生成,不依赖人工打标);抽样 50 单 100% covered。
- replacement 补发单:依赖 Shopify order metafield(`replace_refund` / `order_issue` / `original_order_if_replaced_`)。**这三个 metafield 未被 Fivetran 同步进 Databricks**(order 表无此列,无独立 metafield 表)→ 已发邮件请 Fivetran 同事开启 order metafield 同步。

**已澄清(更正旧表述)**:
- replacement 订单号**不含 EXC** —— replacement(补发)/ EXC(换货)/ refund(退款)是三类独立订单,report 三类都排除。
- Returnly **已停用** —— `tags LIKE '%returnly%'` 过滤作废,无需接 Shopify tags。
- replacement/refund 现在标在 **metafield**,不再用 note/tag。
- 退货/换货走 Loop(Returnly 替代品),但 Loop 触发的退款仍落 Shopify 原生 refund 表,refund 信号不受影响。

> ⚠️【历史·已被 v3 推翻】下面"EXC+refund 两类"是早期落地模型,对账证伪(残差 1.97%→6.57%)后改为"EXC+replacement 整单排除 + refund 行级净扣"。最终版见顶部速览区 Decision 22 v3。保留作演进记录。

**is_sales_attributable 落地策略 —— 分两步**:
- 第一步(现在):`fact_orders_line` 加 `is_sales_attributable` 列,实现 EXC + refund 两类;notebook 04 预留 replacement 接口 + TODO 注释。
- 第二步(metafield 到位后):补 replacement,重跑 notebook 04。

**下一个 dashboard:page_view report**:
- 销售侧(Units Sold / Net Sales / Unique Orders)— Databricks 现有数据可建。
- funnel 侧(item view / add to cart / 分渠道 session)— 来自 GA4,Databricks **无任何 GA4 ingestion**(现有临时表是手动上传的一周数据)→ 需新接 GA4(待与 ingestion 同事确认)。

**待 Leader 确认**:is_sales_attributable 数据层统一标记方向(Q③);demo 反馈 + 下一个想看的 dashboard(Q④)。

---

## 2026-05-26 及之前 — Slice 1 Day 1-5 实施

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
- **Day 3**:notebook 04 channel DQ 卡点解除。dim_channel 种子重建为真实 TW source 值;notebook 04 改用 classic/personal compute(Serverless 不支持 cache → 全 DAG 重算 + heartbeat timeout);加 source normalization 层(emarsys 大小写归一 / google% URL 编码串归一)。最终 channel DQ 0.318% PASS、product DQ 0.000% PASS,996 万行写入成功。
- **Day 4**:metrics-service 真连 Databricks SQL Warehouse(ServerlessWarehouse)。PAT 被组织禁用 → 改用 OAuth U2M 浏览器登录认证。databricks_client.py 加 connection-mode toggle(databricks/mock 可切换);`_bind_params` 解决两个真连才暴露的问题:date_key 是 BIGINT(date→int yyyyMMdd)、连接器 IN-clause 列表展开不稳(改为服务层受控 SQL 解析 + 引号转义)。definitions.yaml 指标升 v1.1,对齐 dim_channel v2.0 列名(legacy_channel_group→channel_group)。

### Day 5 待办(当时的下个 chat 启动点 — 现已完成)
- Next.js `style-channel-quantity` page 从 mock 改为真连 metrics-service API
- 跑 reconciliation 脚本对账 Panoply Style_selling_df(< 2% trust gate)
- Leader demo(H6 demo script)

### 环境备忘(Day 4 配置)
- metrics-service 连 Databricks 用 OAuth(`.env` 里 DATABRICKS_AUTH_TYPE=oauth,无需 PAT)
- SQL Warehouse:ServerlessWarehouse(http_path 在 .env)
- 起服务:先激活 .venv,再 `uv run uvicorn app.main:app --reload`(在 metrics-service 目录)
- 测试 token:`uv run python gen_test_token.py`
- `.env` 已被 .gitignore 忽略,勿提交

### 环境就绪情况
- Databricks schema `mvdevdatabricks.analytics_platform_32degrees` 权限确认:ALL PRIVILEGES + EXTERNAL USE SCHEMA + MANAGE
- ERS Volume 决策:用共享 `mvdevdatabricks.32degrees.raw_uploads/ers/`(ERS 是全公司产品主数据,放共享 raw zone 是正确架构;无需等同事建独立 Volume — 此决策已作为 Decision 20 补入 PROJECT_CONTEXT)
- notebook 全部存放在 Databricks Workspace `Users/sia.song@32degrees.com/analytics-platform/slice_1/`

### Notebook 01-03 实建细节(已跑通)
- **notebook 01 `dim_date`**:原设计从 Volume 读 Parquet,因新 schema 无 Volume,改为 in-notebook PySpark 直接生成(纯算法,无外部文件依赖)。2922 行,ISO 8601 跨年边界 spot check(2024-12-30→2025-W01,2025-12-29→2026-W01)通过。
- **notebook 02 `dim_channel`**:16 行种子载入成功,但**种子里的 channel_source 值最初是按推测写的(google-ads/meta/klaviyo...),与 TW 真实数据对不上 → 是 notebook 04 FAIL 的根因,已重写为真实 TW source 值**。
- **notebook 03 `dim_product`**:ERS CSV 自动检测为 current 格式(列名 SKU/Style#/Item Description 带空格 + Geodis/Ladder 列)。Decision 19 双格式检测生效。36,680 行,is_complete 全部 true。SKU 主键格式 `TLF60281DRT-067-XS`,vend_id = Style#。

### Notebook 04 关键发现(新 chat 需知)
- **TW 正确的归因表是 `attribution_order_click`**,不是 `attribution_order`(后者只有 9 列,无 channel 信息)
- `attribution_order_click` 关键列:`_triple_whale_order_id`(STRING,join key)、`source`(channel)、`click_date`(timestamp,last-touch 去重用)
- join key 映射:Shopify `order.id`(BIGINT,cast STRING)↔ TW `_triple_whale_order_id`(STRING)
- Shopify `order` 表**无 `tags` 列**;`order_line.order_id` 是 BIGINT;`order_line.sku` 存在
- **TW join 成功率高**:990 万行中 unmatched 仅 0.280%(PASS)
- **[Known-issue] `attribution_order_click` 是多租户原始落地表**:`source` 列长尾里出现非 32D 品牌(`DuckaDilly Newsletter` / `Catalinbread Newsletter` / `HealthRangerStore.com` 等),说明该表未按 32D 账号过滤。**对 Slice 1 无影响** —— 跨源 join 以 `_triple_whale_order_id`(= 全局唯一的 Shopify order.id)为 key,外部品牌的点击 join 不上 32D 订单,天然被隔离,不进 fact 表。唯一代价是 ETL 读了比实际需要更大的表(性能,Slice 1 可接受)。建议未来在 ingestion 层按 account_id 过滤作为成本优化项。

> ⚠️【历史·已解决】下面"channel DQ FAIL 44.5%"是 Day 2-3 排查期间的卡点笔记。根因(dim_channel 种子用推测值)已通过重建种子 + source normalization 解决,最终 channel DQ 0.318% PASS。保留作排查记录。

- **当时 channel DQ FAIL:44.5% 的行 channel_key=0(unknown)**;根因:dim_channel 种子的 channel_source 值与 TW `attribution_order_click.source` 实际值不匹配;DQ-as-Gate 按设计拦截坏数据,未写入表 ✅
- **当时第一步要跑的 SQL**:
\```sql
SELECT source, COUNT(*) AS cnt FROM mvdev_federated_catalog.triple_whale.attribution_order_click GROUP BY source ORDER BY cnt DESC;
\```
  两种可能:情况 A TW source 只是名字写法不同 → 改种子名字重跑;情况 B 那 44% source 是 NULL/空 → 决定归到哪个 channel。(实际为情况 A + normalization)

> ⚠️【历史·已采纳并实现】下面是 notebook 04 surrogate key 的性能优化笔记,已采纳(改用 monotonically_increasing_id 零 shuffle)。注意代码片段里的 `is_refunded` 列在 Decision 22 v3 已废弃删除,现行 fact 用 refunded_quantity + is_sales_attributable,以顶部速览区为准。

### Notebook 04 性能优化点(已实现)
- Section 8 生成 surrogate key `order_line_key` 原用无 partitionBy 的 `Window.orderBy()` → 全量 shuffle,跑了 1 小时+;改用 `F.monotonically_increasing_id()` 零 shuffle:
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

### Day 4-5 计划(已完成)
- Day 4:`metrics-service/app/databricks_client.py` 把 mock 换成真实 Databricks SQL 连接
- Day 4.5:数据正确率验证 — 用 Panoply `Style_selling_df` 对比新平台,< 2% trust gate
- Day 5:端到端 wire-up + Leader demo

---

## 2026-05-19/20 — Pre-permission preparation(P0 + H 大批量交付)⭐⭐⭐

### 完成任务汇总(P0 + H)
- ✅ Task A-D:Decision Log / 架构文档 / dim_date 脚本 / 4 notebook 骨架
- ✅ Task E:definitions.yaml 追加 quantity_by_style_channel_week + main.py 泛型 filter + databricks_client mock
- ✅ Task F:Next.js `style-channel-quantity` page(跑通验证 OK)+ API proxy 白名单转发 + dashboards 列表入口
- ✅ Task G:4 张 Slice 1 表 DQ YAML(dim_date/dim_channel/dim_product/fact_orders_line)
- ✅ Task H2/H4/H5:Reconciliation 脚本 / legacy_panoply_etl.md v3 / Decision Log 17-19
- ✅ Slice 1 Day 2-3:notebook 01/02/03 真实建表,notebook 04 卡 channel DQ(后已解决)

**总览**:权限到位前的"零返工准备日",一日内完成 7 个任务交付,所有 Slice 1 Day 2-5 代码层 + 设计层 + 工具层全部就绪。

#### Task A:Decision Log 10-16 写入 PROJECT_CONTEXT.md ✅
- 7 条架构决策从备注状态正式归档:Vertical Slice / ISO 8601 / SCD1 YAGNI / Schema-ETL 解耦 / Channel meta-category 显式建模 / Dual-display channel / `is_paid` forward-looking

#### Task B:Slice 1 Architecture Design Doc ✅ ⭐⭐⭐
- 文件:`docs/architecture/slice_1_design.md`(~700 行,19 sections)
- 覆盖:Executive summary / 5 success criteria / 数据源(3 源)/ 星型模型 ER 图 / ETL 模块划分 / **Cross-source Join Strategy(技术核心)** / DQ Plan / Performance / Schema Evolution & Rollback / Metrics Layer Contract / Frontend wire-up / Testing / 5-day Deployment Run Order / Risk Register / Open Questions
- 面试讲项目时直接可展示的工程化文档,体现 "Design Before Code" 工程实践

#### Task C:`generate_dim_date.py` 本地脚本验证 ✅
- 跑通 CSV 输出(2922 行,2023-01-01 至 2030-12-31);验证 ISO 8601 边界 case(2024-12-30 → ISO 2025-W01)

#### Task D:4 个 PySpark Notebook 骨架 ✅ ⭐⭐⭐⭐⭐
- 位置:`databricks-notebooks/slice_1/`
- `01_build_dim_date.py` — ISO 8601 双 spot check(2024-12-30 + 2025-12-29 跨年边界)
- `02_seed_dim_channel.py` — 版本化 seed SQL 驱动 + dual-display 验证
- `03_build_dim_product.py` — **ERS 双格式 schema-detection 自动识别**(legacy + post-2026 redesign)+ 三 pass 优雅降级
- `04_build_fact_orders_line.py` ⭐ — 技术核心:Last-touch Window 去重(`row_number() over (partition by tw_order_id order by position desc, click_date desc)`)/ Cross-type join(Shopify BIGINT cast STRING ⨝ TW STRING)/ DST-aware 时区(`from_utc_timestamp('America/New_York')`,修正 legacy 静态 -5h bug)/ Multi-tier DQ(PASS < 0.5% / WARN 0.5-2% / FAIL ≥ 2%,基于 0.15% baseline 校准)/ Broadcast joins + Z-ORDER / Smoke vs Full run mode / Idempotent overwrite

#### Task H2:Reconciliation Methodology + Tooling ✅ ⭐⭐⭐⭐
- 位置:`docs/reconciliation/`;5 个产出:README methodology / 新平台 SQL / Panoply legacy SQL / Python diff 脚本 / Excel 彩色报告生成
- **PASS/WARN/FAIL/MISSING** 四级分类 + 颜色编码,Leader-readable;完成本地 dry-run 验证
- **Demo 1 的信任核心物料**:Day 5 跑一下出报告,Leader 看到 < 2% diff 立刻信任迁移

#### Task H5:Decision Log 17-19 + Remaining Tasks Tracker ✅
- Decision 17: DST-aware timezone correction;Decision 18: Multi-tier DQ SLO with empirical baseline calibration;Decision 19: ERS dual-schema ingestion

#### Task H4:Phase 4 Workflows Orchestration Design Doc ✅ ⭐⭐⭐⭐
- 文件:`docs/architecture/phase4_orchestration_design.md`(~750 行,17 sections)
- 覆盖:DAG 拓扑 / 触发策略 / Retry policy / **DQ-as-Gate Pattern**(简历核心)/ Slack/Email 告警 / **Staged Migration: Full → Incremental Load with updated_at watermark + 2-day lookback** / Idempotency / Config as Code / **Workflows vs Airflow Trade-off**(面试 canonical question 答案)/ Risk Register / 5-day 实施计划

**本日产出量化**:7 个任务全部 commit + push GitHub;新增 Decision 10-19(10 条架构决策);约 25-30 条新简历金句;~3000 行代码 + 文档;8 次 git push

**新增简历核心关键词**(本日精华):
- **工程化思维**:Design Before Code(authored 700-line + 750-line architecture design docs)/ Schema Evolution Tolerance(ERS dual-format auto-detection)/ Legacy Bug Correction(DST timezone fix)/ Multi-tier DQ SLO Calibrated Against Empirical Baseline / DQ-as-Gate Pattern(production pipeline integrity contract)/ Staged Migration Strategy(full → incremental with watermark)/ Forward-looking Design(`is_paid` flag for slice 4+ ROAS)
- **技术核心**:Deterministic Multi-touchpoint Deduplication via Window Function / Cross-source Heterogeneous-type Join(BIGINT ↔ STRING)/ Graceful Degradation Entity Resolution(three-pass: exact → fallback → sentinel)/ Broadcast Join Optimization for Small Dimensions / Delta Lake Partition + Z-ORDER Physical Layout Tuning
- **Stakeholder & Process**:Quantitative Reconciliation Methodology(< 2% diff threshold as trust gate)/ Multi-channel Alerting(Slack + Email + Success Digest)/ Workflows vs Airflow Trade-off with Decision-flip Conditions

**关键学习**:
- **零返工保证策略奏效**:所有今日工作都基于已锁定的 DDL v1.1 + 已探测的 schema(99%+ match),没有任何因数据未来变化导致返工的风险。
- **反工作惯性纪律**:今晚多次出现"再做一个"的冲动,Claude 协助识别为焦虑驱动而非产出需求,引导收尾。坚持北极星第五原则:**基于反馈迭代,不焦虑式堆砌**。
- **一次性批量贴代码 > 分多次切换**:Task E/F/G/H3 共同点都是需要看现有代码风格,锁定一次性贴完,避免上下文切换成本。

---

## 2026-05-18 — Day 1 Slice 1 完整交付 ⭐⭐⭐

**方法论转变(关键)**:经讨论锁定采用 **Vertical Slice(垂直切片)** 方法论交付 Phase 2B/3,替代"先全部建完再上线"的瀑布式。每个切片从数据源到前端端到端打通,逐切片扩展数仓。

**切片 1 范围**:服务 `Style-channel (quantity)` page 端到端打通 → 给 Leader 看 demo;数据窗口 2025-07-01 起;4 张表;预计 5 天(Day 1 设计 → Day 2-3 ETL → Day 4 服务层 → Day 5 前端)。

**Day 1 完整产出(4 个任务)**:

#### 任务 1:星型模型 DDL ✅
- 文件:`docs/data_modeling/star_schema_ddl.sql`(v1.0 → v1.1)
- v1.1 调整:dim_channel 砍 `is_web_attributed` / `is_operational`,重命名 `ga4_channel_name` → `legacy_channel_group`;完整 header 含 changelog / purpose / star schema 图 / 5 大设计决策 / 执行 prerequisites

#### 任务 2:PROGRESS.md 更新 ✅

#### 任务 3:dim_date 种子数据生成脚本 ✅
- 文件:`scripts/generate_dim_date.py` + `scripts/.gitignore`
- 纯标准库生成 2023-01-01 至 2030-12-31(2,922 行)+ 可选 Parquet;内置 ISO 8601 边界周 sanity check;`.gitignore` 排除生成的 .csv / .parquet(脚本是 source of truth)

#### 任务 4:dim_channel 种子 SQL ✅
- 文件:`docs/data_modeling/dim_channel_seed.sql`;16 行;TRUNCATE-then-INSERT 幂等;Dual-display taxonomy(channel_source TW 原值 + legacy_channel_group GA4 风格);含验证查询

**Day 1 关键设计决策(已锁定,见 Decision 10-16)**:Vertical Slice / ISO 8601 only / SCD1+YAGNI / Schema unbounded ETL bounded / Channel taxonomy alignment with TW / Dual-display channel / is_paid forward-looking

**TW pipeline owner 澄清的两个 meta-category**:`Non-attributed`(其他销售渠道如 Shopify Shop app,非站内流量)/ `Excluded`(exchanges 或 draft orders 等运营订单)— 选择保留并显式标注(显式建模 > 静默丢弃)

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

### Track 1 §5.1 — 第一个 PBI page 反向工程(2026-05-18)⭐
**目标 page**:`Style-channel (quantity)`(PBI 第 2 个 tab);**产出**:`docs/existing_data_inventory.md` §5.1(8 个子节)
- §5.1.1 Page 全景 / §5.1.2 Visual 详解 / §5.1.3 数据源追溯(100% 来自 `Style_selling_df`)/ §5.1.4 ⭐ 3 个简历级洞察(Conformed fact 服务多角色 / BI 派生 vs 源系统物化时间口径风险 ⭐ / 行级粒度不可替代性)/ §5.1.5 新平台方案 / §5.1.6 Channel 口径迁移 / §5.1.7 待 Leader 对齐 3 决策 / §5.1.8 检查清单

**新增简历金句**(3 条):
- "Validated Kimball's conformed fact principle in legacy system reverse engineering — identified a single fact table serving buyer / marketing / merchandiser personas via dimensional slicing."
- "Identified a latent risk in legacy BI report where tool-derived date hierarchy and source-system-precomputed date fields could disagree on boundary weeks; resolved by introducing a unified `dim_date` conformed dimension."
- "Architected a dual-taxonomy channel dimension to handle attribution platform migration (GA4 → Triple Whale) with non-overlapping data windows."

**关键词**:BI Reverse Engineering / Requirements Reverse Engineering / Conformed Dimension Design / BI Layer Decoupling / Date Semantics Standardization

---

## 2026-05-15 — TW backfill 验证通过,Phase 2B/3 阻塞解除 🚀

**验证结果**(`existing_data_inventory.md` Appendix A.2):

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

**全部 11 个月 match rate ≥ 99.85%,远超 90% 阈值。**
**业务意义**:跨源 join 健康基线确认为 99%+(之前误判的 44% / 22% / 27% 缺口都已澄清);TW 实际追踪所有 Shopify 订单(含 direct/unattributed,channel 标记为 'direct')。

### Panoply Legacy 反向工程(2026-05-15 完成 95%)⭐⭐
**起因**:做 Track 1 文档 Step 4(PBI Dashboard 映射)时,意识到必须先完整理解过去 Panoply ETL 体系,才能准确映射新平台。
**产出**:`docs/legacy_panoply_etl.md`(v3,~780 行)— 盘点 6 大业务域 ~30 张 query model;识别 13 个工程亮点;"Legacy → New Platform"演进映射;11 个英文简历 Bullets + 2 个 STAR 面试故事

**6 大业务域**:1 销售归因(行级+订单级双粒度)/ 2 退货分析(双路径)/ 3 替换分析(双路径)/ 4 运费成本 / 5 订单篮子行为 / 6 产品主数据 + Basket

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

**剩余 5%**:其他 PBI page 的底层数据来源 — 不阻塞,可在 Section 5 边做边补

---

## 2026-05-05 ~ 14 — 数据接入校验 + Track 文档

### 数据接入校验与协调(2026-05-05 至 2026-05-15)
- ✅ Fivetran Shopify connector 错连 Appaman → 已修复至 32Degrees(8 日累计差异 0.5%)
- ✅ TW `attribution_order` backfill 多轮完成 → 2026-05-15 验证通过,全部月份 ≥ 99.85% match rate
- ✅ 跨源 join 健康基线确认为 ≥ 99%(之前误判的 44% / 22% / 27% 是数据未完整时的伪基线)
- ✅ Source reconciliation:Databricks Shopify vs Panoply 8 日累计差异 0.5%

### Track 1 — 数据资产探索(2026-05-05 完成)
- 摸清 Databricks 上 13 张表的结构和粒度;数据接入工具确认:Shopify 走 Fivetran,TW 走 custom pipeline

### Track 3:DQ 框架代码骨架(2026-05-13 完成)⭐
- 基于抽象基类的可扩展架构(BaseChecker)+ 4 种 checker(not_null / unique / range / freshness)+ YAML 配置驱动(2 示例)+ Runner + Reporter(console + JSON)+ 15 个测试场景全过;位置:`metrics-service/data_quality/`

### Track 1 文档 — `existing_data_inventory.md`(2026-05-14 完成 Step 1-3)
- Section 1 Executive Summary / 2 Shopify 8 表详解 / 3 TW 5 表详解 / 4 其他 Schema 边界声明(扫 8 个相关 schema)/ 5.1 Style-channel page 反向工程 / 6 Open Issues(4 个,根因+影响+方案)/ 7 Appendix(5 个可复用 SQL)

---

## 2026-04 — Phase 1 + 2A + Project Brain

### Phase 1:Portal MVP(2026-04 完成)
- Next.js portal 跑通(登录 + 列表页 + 2 个详情页);Mock 数据按 Data Contract 设计;Data Contracts 写好(Shopify, Triple Whale);部署 GitHub

### Phase 2A:Metrics Service(2026-04 完成)
- FastAPI 框架 + uv 依赖;4 个指标(YAML + version + changelog);JWT 鉴权 + CORS;Mock Databricks client(抽象接口);Next.js 改造完成,通过 FastAPI 取数

### Project Brain 搭建(2026-04 完成)
- NORTH_STAR / PROJECT_CONTEXT / ROADMAP / PROGRESS / SIA_PROFILE / streaming_module_plan;Project Instructions 配置完成

---

# ═══════ 💎 简历素材沉淀(完整保留)═══════

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

### Deterministic Seed Data Generation — dim_date(2026-05-18)⭐
设计可重跑、可测试的种子数据生成器替代 in-warehouse SQL 计算:
- Python 标准库 `datetime.isocalendar()` 实现 ISO 8601 边界周(避免 SQL 方言行为不一致)
- 内置 sanity check 验证 ISO 8601 跨年周边界(如 2024-12-30 → ISO 2025-W01)
- 双输出格式:CSV(可读、diff-friendly)+ Parquet(Databricks 加载最快)
- 实践 "commit generators, gitignore artifacts" 原则
- 位置:`scripts/generate_dim_date.py`

**关键词**:Deterministic Seed Generation / Python over SQL for Date Semantics / Embedded Sanity Checks / Idempotent Pipelines / Generators-as-source-of-truth

### Dual-Display Channel Dimension Design(2026-05-18)⭐⭐
设计双显示口径的 channel 维度表,服务多种 stakeholder 认知:
- `channel_source` 保留 Triple Whale 原值 → 与 TW UI 一致,服务运营团队
- `legacy_channel_group` 加入 GA4 风格分组 → 服务高管对 PBI 报表的认知惯性
- 同一 dim 表服务两种用户,不强迫任何一方学对方的术语
- 体现 Conway's Law 在数据建模中的应用 — 组织结构影响 schema 设计
- 前瞻设计 `is_paid` flag 服务切片 4+ ROAS 指标(避免后续 ALTER TABLE)
- 16 行预先 INSERT 种子 SQL,版本控制业务分类决策
- 位置:`docs/data_modeling/dim_channel_seed.sql`

**关键词**:Dual-Display Dimension / Conway's Law / Stakeholder-Aware Schema Design / Forward-Looking Dimension Flags / Version-Controlled Seed SQL / Platform Migration Cognitive Cost Mitigation

> 📌 2026-05-27 之后(Slice 1 收尾 + Amazon)的简历金句,已统一沉淀到 `docs/RESUME_HIGHLIGHTS.md`(简历金句单一正源)。包括:Reconciliation-Driven Model Correction / Restock-type-aware Line-level Refund Netting / Fully-itemized Residual Attribution / Quantified Legacy Accuracy Gap / API Ingestion + Medallion / Idempotent MERGE / Multi-domain Platform with Prefix Isolation / Source-extensible Platform 等。投简历/面试请看 RESUME_HIGHLIGHTS.md。

---

# ═══════ 🔖 长期备忘 ═══════

### 备忘 0:简历金句单一正源
`docs/RESUME_HIGHLIGHTS.md` —— 投简历/面试只看这个;详细出处散在 `legacy_panoply_etl.md §8` / `PROJECT_CONTEXT.md` Decision Log / 各 completion summary / 本文件简历素材沉淀区。

### 备忘 1:Page_view report 数据导出(同事需求)
**状态**:🟢 已解决(Panoply 已修复,Sia 直接在 Panoply 跑原 SQL 给同事)
**完整依赖链已分析**(下次新平台做这个 page 时直接用):
```
Page_view
├── Shopify_sales_data
│   ├── shopify_orders_order ✅
│   ├── shopify_orders_order_line_items ✅
│   ├── customer_type_info ⚠️ 需重建
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
> 注:dim_channel 后续重建为 v2.0(Decision 21,channel_group 上卷层级 + is_meta_category,23 行),以 star_schema_ddl.sql v2.0 为准。

### 备忘 4:Excluded 订单分析(切片 3 退货可能需要)
**Open question**:做退货 / 替换分析时,Excluded(exchanges/drafts)订单是否需要看?
- 当前设计:`Excluded` channel 跟其他 channel 一样显示,不特殊处理
- 切片 3 时可能需要:看 exchange 订单原本来自哪个 channel → 需要 fact 表加 `original_channel_key` 字段
- 现在不做:不阻塞,标记备忘后续处理

### 备忘 5:待办切片(report 桶里值得进项目的少数,平台栈之后再做)
- **Slice 2 — Revenue page**:dollar 粒度净退款 + 折扣/税口径 + AOV。新语义(比件数多一层),值得进项目。
- **Slice 3 候选 — Customer Cohort / 复购次数**:order history 窗口函数 + first-time/returning 状态推导
  (见备忘 §1 亮点 #15)。有新建模能力,值得进项目。
- 其余 report(refund&replacement、各种换指标统计)= 纯工作交付,warehouse 建掉,不进项目。
- **优先级**:先走平台栈 Phase 4→4.5→5→6;Slice 2/3 作为后续切片,不阻塞平台栈。
---

# ═══════ 📌 新 chat 启动提醒 ═══════

### 项目基础信息
- 用户:Sia(GitHub: sichensong-99)| 公司:32Degrees(保暖服装品牌,2025-07-01 启用 Triple Whale)
- 项目路径:`C:\Users\sia.song\analytics-platform` | 环境:Windows 11 + PowerShell + VS Code
- 风格:中英文混用,代码要完整版,命令要解释清楚,决策要明确推荐

### 数据源现状
- **Shopify** @ `mvdevdatabricks.shopify_32degrees`:✅ ready(11.45M 订单,23 张表见备忘 §2)
- **TW** @ `mvdev_federated_catalog.triple_whale`:✅ ready(全部月份 ≥ 99.85% match rate)
- **ERS 产品主数据**:✅ 月度 CSV 上传至共享 `mvdevdatabricks.32degrees.raw_uploads/ers/`(Decision 20)
- **Amazon FBA 入库**(SP-API):✅ 自建 ingestion(Decision 23/24)
- **数据完整性判定标准**:跨源 monthly match rate ≥ 90%(实际 99%+)

### 工作原则
- **任何建议必须用 NORTH_STAR.md 的 5 大原则过滤一遍**
- 已选定方案不要再翻盘,有疑问参考 PROJECT_CONTEXT.md 的 Decision Log
- 用户偏好"先想清楚再动手",先讲全局规划再讲细节
- 用户严格反对返工,建议必须区分"0 返工"和"可能返工"
- 用户容易信息过载,**一次给一个具体任务**,不要无限发散

### 关键文档清单
- `NORTH_STAR.md` — 最高决策原则
- `PROJECT_CONTEXT.md` — 项目背景、架构、决策(Decision 1-24)
- `ROADMAP.md` — 阶段计划(已更新为 vertical-slice + Amazon)
- `PROGRESS.md` — 本文档,当前进度
- `SIA_PROFILE.md` — Sia 偏好
- `streaming_module_plan.md` — Phase 4.5 计划
- `docs/RESUME_HIGHLIGHTS.md` — 简历金句单一正源 ⭐
- `docs/existing_data_inventory.md` — Track 1 数据资产盘点(含 §5.1)⭐
- `docs/legacy_panoply_etl.md` — Panoply 反向工程(13 个简历亮点的金矿,待补 #14/#15)⭐
- `docs/architecture/slice_1_design.md` — Slice 1 架构设计(~700 行)
- `docs/architecture/slice_1_completion_summary.md` — Slice 1 完结总结
- `docs/architecture/phase4_orchestration_design.md` — Phase 4 调度设计(~750 行)
- `docs/architecture/amazon_ingestion_design.md` — Amazon ingestion 设计
- `docs/data_modeling/star_schema_ddl.sql` — 星型模型 DDL v2.0(含 Amazon gold)⭐
- `docs/data_modeling/dim_channel_seed.sql` — channel 种子数据
- `docs/demo/leader_demo_script.md` — Leader demo script
- `scripts/generate_dim_date.py` — dim_date 种子生成器

---

# ═══════ 🔄 进度更新历史 ═══════

| 日期 | 完成内容 | 下一步 |
|---|---|---|
| 2026-04-28 | Phase 2A 完成,Project Brain 搭建完成 | 进入 Track 1 |
| 2026-05-05 | Track 1 数据探索完成,发现 2 个上游数据问题并发邮件,业务主体确认为 32Degrees | 阻塞期推进 Track 3 |
| 2026-05-13 | Shopify 数据修复完成;TW backfill 至 2025-07-01;Track 3 DQ 框架完成并推送 GitHub | 启动 Track 1 文档 |
| 2026-05-14 | Track 1 文档 Step 1-3 完成;TW 二次 backfill;发 follow-up 邮件给 Cal | Track 1 文档 Step 4 |
| 2026-05-15 | TW backfill 验证全月 ≥ 99.85%;Panoply 反向工程 95%,产出 legacy_panoply_etl.md v3;13 个简历亮点 | 启动 Section 5 |
| 2026-05-18 (上半) | §5.1 完成,3 个简历洞察;Decision 9 加入;Page_view 同事需求经 Panoply 解决 | quantity page 作为切片 1 |
| 2026-05-18 (EOD)⭐⭐⭐ | Day 1 完整交付 4 任务;Vertical Slice 锁定;Decision 10-16 锁定;17 条简历金句一日产出 | 等权限 → Day 2 |
| 2026-05-19/20 ⭐⭐⭐ | 7 个 P0/H 任务批量交付;Decision 17-19;Phase 4 设计文档;25-30 条金句 | 等独立 schema |
| 2026-05-21~26 | dim_channel v2.0 重建(Decision 21);notebook 01-04 全建;真连 Databricks;Day 5 对账谜题破解 | 读 Panoply 源码定口径 |
| 2026-05-27 | Slice 1 对账过 trust gate(−1.51%);Decision 22 v3 锁定;三个终版交付 | Amazon + metafield |
| 2026-05-28 | Amazon ingestion 90%(三 notebook + 调度 + 后端 + 前端);Decision 23-24 | 🚫 等 Databricks 权限恢复 |