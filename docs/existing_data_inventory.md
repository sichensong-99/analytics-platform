# Existing Data Inventory

> **Purpose**: 盘点 the retailer 内部分析平台所依赖的全部数据资产,作为 Phase 2B/3 数仓建模、Dashboard 设计与数据治理的输入。
>
> **Scope**: Databricks Lakehouse 内已接入的数据源(Shopify via Fivetran + Triple Whale via custom pipeline),覆盖订单、归因、客户三大业务域。
>
> **Last Updated**: 2026-05-14
> **Maintainer**: Sia
> **Status**: Living document — 数据质量状态会随上游修复持续更新

---

## 1. Executive Summary

### 1.1 数据源全景

| 数据源 | 业务作用 | 接入方式 | Catalog / Schema | 状态 |
|---|---|---|---|---|
| Shopify | 订单事实(收入、客户、退货)| Fivetran (managed ELT) | `analytics_catalog.shopify_raw` | ✅ Ready |
| Triple Whale | 营销归因(渠道、广告)| Custom Pipeline | `federated_catalog.triple_whale` | 🟡 1-2 月数据补全中 |

### 1.2 关键决策

- **Shopify** 走 Fivetran:作为 SaaS 标准源,采用 industry-standard managed ELT 工具加速接入,信任 Fivetran connector 完整性
- **Triple Whale** 走 custom pipeline:TW 作为非标 SaaS,使用公司自有 pipeline 拉取以获得字段级灵活性
- **Source of Truth**:Shopify 是订单事实的最终来源;TW 用于归因分析,**不作为订单总数的依据**
- **跨源关联**:Shopify `order.id` ↔ TW `attribution_order._triple_whale_order_id`(数据类型需 cast 为 string)

### 1.3 数据规模(截至 2026-05-14)

| 维度 | Shopify | TW |
|---|---|---|
| 总订单数(2025-07-01 至今)| 2,439,958 | 2,005,533 |
| 时间跨度 | 2014 至今(回溯 12 年+)| 2025-07-01 至今(TW 系统启用日)|
| 月均订单量 | 200K - 400K(季节性) | 200K - 400K(健康月份) |

---

## 2. Shopify 数据源详解

### 2.1 接入信息

| 项目 | 详情 |
|---|---|
| **数据源系统** | Shopify Admin API |
| **同步工具** | Fivetran |
| **目标位置** | `analytics_catalog.shopify_raw` |
| **业务主体** | the retailer(自营 Shopify store)|
| **同步频率** | 日增量(预计每日 1 次)|
| **数据完整性** | ✅ 已通过 source reconciliation 验证(vs Panoply,8 日累计差异 0.5%)|
| **可用历史范围** | 完整历史(回溯至 2014 年首单)|

### 2.2 表清单与粒度

Shopify 在 Databricks 共 **8 张表**,按业务域分类如下:

#### 📦 订单域(Order Domain)

##### Table: `order`
| 项目 | 详情 |
|---|---|
| **粒度** | 1 行 = 1 个订单 |
| **主键** | `id` (BIGINT) |
| **业务键** | `name` (e.g., `#12769985`) |
| **行数(2025-07-01 至今)** | ~2.4M |
| **用途** | 订单事实表的核心数据源,所有收入指标的基础 |

**核心字段**:
- 标识:`id`、`name`、`order_number`
- 客户:`customer_id`、`email`
- 时间:`created_at`、`processed_at`、`cancelled_at`、`closed_at`、`updated_at`
- 金额:`total_price`、`subtotal_price`、`total_tax`、`total_discounts`、`current_total_price`
- 状态:`financial_status`(paid/refunded/etc.)、`fulfillment_status`
- 地址:`shipping_address_*`、`billing_address_*`(扁平化字段,可直接用于地理分析)
- 来源:`source_name`、`referring_site`、`landing_site_base_url`
- UTM:嵌套在 `note_attributes`(JSON 字符串,需解析)
- Fivetran 元数据:`_fivetran_synced`、`_fivetran_deleted`

**已知特性**:
- `note_attributes` 包含 UTM 参数(`utm_source`、`utm_medium`、`utm_campaign`),**Shopify 自身的归因数据**,可与 TW 归因交叉验证
- `total_price` 包含税与折扣后的最终金额
- 地址字段已扁平化(不是嵌套 JSON),简化了下游建模

---

##### Table: `order_line`
| 项目 | 详情 |
|---|---|
| **粒度** | 1 行 = 1 个 SKU 行项 |
| **主键** | `id` |
| **外键** | `order_id` → `order.id` |
| **行数(2025-07-01 至今)** | ~5M+(每订单多 SKU)|
| **用途** | 商品级销售分析、SKU 维度建模、`dim_product` 提取源 |

**核心字段**:
- 标识:`id`、`order_id`
- 商品:`product_id`、`variant_id`、`sku`、`title`、`vendor`、`variant_title`
- 数量价格:`quantity`、`price`、`total_discount`
- 履约:`fulfillment_status`

**已知特性**:
- the retailer 没有独立的 `product` 表,商品维度信息全部在此表
- 99% 的 `vendor` = 自营品牌(the retailer)
- 可作为 `dim_product` 与 `dim_variant` 的数据源(取去重后)

---

#### 🔄 退货域(Return Domain)

##### Table: `return`
| 项目 | 详情 |
|---|---|
| **粒度** | 1 行 = 1 次退货 |
| **主键** | `id` |
| **外键** | `order_id` → `order.id` |
| **用途** | 退货事实表的核心数据源 |

##### Table: `return_line_item`
| 项目 | 详情 |
|---|---|
| **粒度** | 1 行 = 1 个退货 SKU 行 |
| **外键** | `return_id` → `return.id`、`order_line_item_id` → `order_line.id` |
| **用途** | SKU 级退货分析 |

##### Table: `return_shipping_fee`
| 项目 | 详情 |
|---|---|
| **粒度** | 1 行 = 1 笔退货运费 |
| **外键** | `return_id` → `return.id` |
| **用途** | 退货成本分析 |

##### Table: `order_line_refund`
| 项目 | 详情 |
|---|---|
| **粒度** | 1 行 = 1 笔订单行级退款 |
| **外键** | `order_line_id` → `order_line.id` |
| **用途** | 行级退款金额跟踪(部分退款场景)|

---

#### 👤 客户域(Customer Domain)

##### Table: `customer`
| 项目 | 详情 |
|---|---|
| **粒度** | 1 行 = 1 个客户 |
| **主键** | `id` |
| **业务键** | `email` |
| **用途** | `dim_customer` 的核心数据源 |

##### Table: `customer_tag`
| 项目 | 详情 |
|---|---|
| **粒度** | 1 行 = 客户的 1 个标签(M:N 关系)|
| **外键** | `customer_id` → `customer.id` |
| **用途** | 客户分群(VIP、re-engaged 等)|

---

## 3. Triple Whale 数据源详解

### 3.1 接入信息

| 项目 | 详情 |
|---|---|
| **数据源系统** | Triple Whale Attribution Platform (SaaS) |
| **同步工具** | Custom Pipeline(公司自研) |
| **目标位置** | `federated_catalog.triple_whale` |
| **业务主体** | the retailer |
| **数据起始日** | 2025-07-01(the retailer 启用 TW 的日期,不是 TW 的数据 retention 限制) |
| **同步频率** | 日增量(已观察:5/12 后开始日级 sync) |
| **数据完整性** | 🟡 **2026-01 和 02 月数据不完整**(match rate 22% / 27%,见 §6 Open Issues) |
| **归因模型** | TW 默认 last-click 7-day,可在 `attribution_order_click` 看到 linear / linearAll 等多模型 |

### 3.2 业务定位与边界

**TW 是营销归因数据,不是订单事实数据。**

- ✅ **应该用 TW 做的**:渠道贡献分析、广告 ROAS、多触点归因、营销活动效果
- ❌ **不应该用 TW 做的**:订单总数统计、收入总额(应该用 Shopify)
- ⚠️ **跨源关联原则**:Shopify 是订单事实的 source of truth,TW 提供"这个订单来自哪个渠道"的补充信息

**为什么 TW 订单数 ≈ Shopify 订单数**:
- 经过验证(2025-10 至 2026-03),健康月份 TW 与 Shopify 跨源 join match rate ≥ 92%
- TW 实际追踪 **所有 Shopify 订单**,包括 direct / unattributed 流量(channel 字段标记为 'direct')
- 这与"TW 只追踪有归因来源的订单"的常见误解不符

### 3.3 表清单与粒度

TW 在 Databricks 共 **5 张表**,按归因层级分类:

#### 📊 订单归因层

##### Table: `attribution_order`
| 项目 | 详情 |
|---|---|
| **粒度** | 1 行 = 1 个订单(订单级归因汇总)|
| **主键** | `_triple_whale_order_id`(对应 Shopify `order.id`)|
| **业务键** | `order_name`(对应 Shopify `order.name`)|
| **行数(2025-07-01 至今)** | ~2M |
| **用途** | `fact_orders_with_attribution` 的数据源,与 Shopify 订单 join |

**核心字段**:
- 标识:`_triple_whale_order_id`、`order_name`、`client`、`_triple_whale_shop`
- 时间:`created_at`(订单创建时间,UTC)、`_synced_at`(pipeline 同步时间)
- 金额:`total_price`、`currency`
- 客户:`customer_id`

**已知特性**:
- 此表**不包含 channel 与 campaign 字段** — 那些数据在 `attribution_order_click`
- `_triple_whale_order_id` 是 Shopify `order.id` 的 string 形式,join 时需要 `CAST(s.id AS STRING)`

---

#### 🖱️ 点击归因层(多触点)

##### Table: `attribution_order_click`
| 项目 | 详情 |
|---|---|
| **粒度** | 1 行 = 1 个订单的 1 个广告点击(1 订单 N 点击)|
| **外键** | `_triple_whale_order_id` → `attribution_order` |
| **行数** | ~5x of attribution_order(平均每订单 ~5 个 touchpoint)|
| **用途** | 多触点归因分析、`dim_channel` / `dim_campaign` 提取源 |

**核心字段**:
- 标识:`_triple_whale_order_id`、`click_date`
- 归因:`attribution_model`(linear / linearAll / 等)、`position`(touchpoint 序号 0-N)
- 渠道:`source`(google-ads / bing / meta / impact / organic_and_social / 等)
- 广告层级:`campaign_id`、`adset_id`、`ad_id`

**已知特性**:
- 这是 TW 数据中的 **金矿** — 多触点归因明细
- 同一订单会有多行,代表用户转化前经过的多个 touchpoint
- 同一订单可能同时存在多种 `attribution_model`,每种模型独立给出归因结果
- 时间维度上,`click_date` 可能远早于 `attribution_order.created_at`(例如 10 月点击 → 12 月转化)

**典型查询场景**:
```sql
-- 某订单的完整旅程
SELECT *
FROM attribution_order_click
WHERE _triple_whale_order_id = '7137654571097'
  AND attribution_model = 'linear'
ORDER BY position;
```

---

##### Table: `attribution_order_journey_event`
| 项目 | 详情 |
|---|---|
| **粒度** | 1 行 = 1 个用户旅程事件(比 click 更细)|
| **当前使用计划** | 🚧 暂不纳入 Phase 2B/3 建模 |
| **后续可能用途** | 用户旅程深度分析、L2L (Long Tail Landing) 分析 |

---

#### 📈 预聚合指标层

##### Table: `summary_page_metric`
| 项目 | 详情 |
|---|---|
| **粒度** | 1 行 = 1 个指标 × 1 个时间窗口 |
| **用途** | **作为对账参考**,不作为 fact 表数据源 |

**核心字段**:
- 指标元信息:`metric_id`、`metric_title`、`metric_type`(currency / number / percentage)
- 业务标识:`metric_services`(数据来源服务,如 `["shopify"]`)
- 数值:`value_numeric`、`value_string`
- 时间:`period_start`、`period_end`、`period_kind`(current / previous)

**已知特性**:
- TW 自己已经预聚合的全店 KPI(总销售、新客销售、毛利、广告支出等)
- **可用于对账**:自建数仓 DWS 层算出来的指标,与此表对比,差异 < 5% 视为口径一致
- 不作为 fact 源 — 我们从更底层数据自己算指标,保证指标可信来源可追溯

##### Table: `summary_page_metric_chart_point`
| 项目 | 详情 |
|---|---|
| **粒度** | 1 行 = 1 个时序数据点(`summary_page_metric` 的图表展开)|
| **当前使用计划** | 🚧 暂不纳入 Phase 2B/3 建模 |

---

### 3.4 TW 数据使用决策表

| 场景 | 用哪张表 | 理由 |
|---|---|---|
| 算订单总数、总收入 | ❌ 不用 TW,用 Shopify `order` | Shopify 是订单事实 source of truth |
| 算渠道贡献(channel revenue)| `attribution_order` + `attribution_order_click` | join 后按 channel 分组 |
| 多触点归因分析 | `attribution_order_click` | 唯一含多 touchpoint 数据的表 |
| 广告 ROAS | `attribution_order_click` + 广告支出数据(后续可能接入)| |
| 对账验证 | `summary_page_metric` | TW 已聚合的官方数字,作为基准 |

---

## 4. 其他可用 Schema(已扫描,本项目不纳入)

为了完整记录数据资产边界,Databricks `analytics_catalog` catalog 下还有以下 schema 存在,但**本项目不纳入建模范围**:

| Schema | 内容推测 | 跟本项目关系 |
|---|---|---|
| `erp_ops` | 业务运营表(采购订单 PO / 款式 Style / 库存等,推测来自 ERP)| 🟡 暂不使用,若需要库存/采购维度可再纳入 |
| `amazon_performance` | Amazon 渠道广告数据 | ❌ 不使用 — 渠道归因已由 TW 提供 |
| `meta_performance` | Meta(Facebook/Instagram)广告数据 | ❌ 不使用 — 同上 |
| `google_performance` | Google Ads 数据 | ❌ 不使用 — 同上 |
| `ecom_channel_performance` | 多品牌电商渠道汇总(7 张姊妹品牌缩写表)| ❌ 不使用 — the retailer 不在此 schema 中 |
| `erp_views` | ERP 系统视图 | ❌ 不使用 — 与本项目业务无关 |
| `reports` | 空 schema(无表) | ❌ 不使用 |
| `default` / `information_schema` | Databricks 系统默认 schema | ❌ 不使用 |

### 4.1 数据源边界声明

**本项目仅基于以下两个数据源建模**:
- `analytics_catalog.shopify_raw`(Shopify 订单/退货/客户)
- `federated_catalog.triple_whale`(TW 归因)

**理由**:
1. 与 stakeholder 和 BI Dashboard owner 已对齐数据源范围
2. TW 已聚合所有营销渠道归因数据,无需再独立接入各广告平台
3. 项目目标是替代现有 BI Dashboard,不扩展到新业务域(如库存、采购)
4. 限定数据源边界有助于保持项目 scope 清晰,避免 scope creep

### 4.2 未来可能纳入的数据源

如果未来需要扩展能力,以下 schema 可考虑纳入(不在当前 scope):

- **库存与采购分析** → 探索 `erp_ops` schema(已有 PO / Style / 库存数据)
- **客户旅程深度分析** → 启用 `federated_catalog.triple_whale.attribution_order_journey_event`
- **跨品牌对比** → 协同其他 BI 团队,考虑统一到 `ecom_channel_performance` 模式

---

## 5. BI Dashboard → 新数据源映射

> **目的**:把现有 BI report 每个 page 上的每个 visual 反向工程出来,作为新平台数仓建模与指标定义的需求依据。
>
> **方法**:每个 page 走"全景 → visual 详解 → 数据来源追溯 → 关键洞察 → 新平台对应方案"五段式。

---

## 5.1 Page: `Style-channel (quantity)`

> **报表位置**:Style-Channel report 的第 2 个 tab(共 20+ tabs)
> **服务对象**:Ecom 全团队(buyer / marketing / merchandiser)— 同一份 fact 服务多角色
> **核心业务问题**:每个 style 在每个营销渠道、每周卖了多少件?
> **数据源**:`Style_selling_df`(Panoply 上叫 `Style_selling_dfNEW`,行级 fact)
> **完成日期**:2026-05-18

---

### 5.1.1 Page 全景

整个 page 由 4 个核心元素构成,设计极其简洁:

| # | 元素 | 类型 | 作用 |
|---|---|---|---|
| 1 | 顶部时间滑块(Y/W/D 三粒度切换,2016–2025)| Numeric range slicer | 控制时间窗口 + 时间粒度 |
| 2 | 左侧 slicer panel:`channel` / `season` / `style` | 3 个 Slicer | 维度过滤 |
| 3 | 中间折线图 | Line chart | channel × week 销量趋势 |
| 4 | 右侧矩阵表 | Matrix table with drilldown | style × channel × item × week 销量明细 |

**Page 设计哲学**:折线图(macro view,看趋势)+ 矩阵表(drill-down view,看明细)的经典组合。左侧 slicer 与顶部时间滑块**联动控制**两个 visual。

---

### 5.1.2 Visual 详解

#### Visual 1 — 顶部时间滑块(Date Range Slider)

| 项目 | 详情 |
|---|---|
| **类型** | Numeric range slicer with Y/W/D hierarchy toggle |
| **绑定字段** | `Style_selling_df.day`(单一字段)|
| **当前选择** | 2023–2024 |
| **粒度切换** | Y(年)/ W(周)/ D(日)三键,**由 BI 工具自动从 `day` 派生** year/week 层级 |
| **作用范围** | Page 上**所有** visuals 联动 |

#### Visual 2 — 左侧 Slicer Panel

| Slicer | 绑定字段 | 选项数量 | 备注 |
|---|---|---|---|
| **channel** | `Style_selling_df.channelgrouping` | 11+ | GA4 channel grouping(Affiliates / Email / Paid Search / Organic Search / ...)|
| **season** | `Style_selling_df.season` | ~10+ | 来自 ERS 产品主数据(BAS / BAS-DIS / F22 / F23 / ...)|
| **style** | `Style_selling_df.style`(对应 ERS `vend_id`)| 数百 | 含搜索框 |

> ✅ **隐式过滤器审计**:Page-level filter 里无隐式过滤,所有过滤都通过显式 slicer 完成。新平台保留这个设计原则 — 杜绝"暗箱过滤"。

#### Visual 3 — 中间折线图(Line Chart)

| 项目 | 详情 |
|---|---|
| **图表类型** | Multi-line chart |
| **X 轴** | `year` + `week`(BI 工具自动从 `day` 派生的 hierarchy)|
| **Y 轴** | `SUM(quantity)` |
| **Legend** | `channelgrouping`(每个 channel 一条线)|
| **数据标签** | 显示每个 channel 在每周的具体数字(e.g. `Email 70,297`)|

**业务问题**:"上周 / 本季各渠道卖了多少件?Email 涨势如何?Paid Search 是否在掉?"

**主要使用者**:**Marketing** — 判断各渠道周度表现,评估投放效果

**支撑的具体决策**:
- "Email 渠道周销下滑 → 检查最近 EDM 投放频率"
- "Affiliates 突然飙升 → 看是哪个合作方在推"
- "Paid Search 周度抖动大 → 看预算配置是否有问题"

#### Visual 4 — 右侧矩阵表(Matrix)

| 项目 | 详情 |
|---|---|
| **图表类型** | Matrix with 3-level hierarchical drilldown |
| **Rows(下钻 3 层)** | `style` (UI label `style (week)`) → `channelgrouping` → `Item_description` |
| **Columns** | `year` + `week`(**用 Panoply 表原生 `year` / `week` 字段**,不是 BI 派生)|
| **Values** | `SUM(quantity)` |

**业务问题**:"`STYLE-A` / `STYLE-B` / `SKU-1234` 这几个 style,这几周在各渠道分别卖了多少件?对应 SKU 是哪些?"

**主要使用者**:
- **Buyer**:看 style × week 销量趋势 → 决定补货 SKU 与数量
- **Merchandiser**:看 style × channel 交叉 → 决定哪些 style 在哪个 channel 推
- **Marketing**:从 Item_description 层下钻 → 看具体 SKU 在哪个 channel 表现好

⭐ **关键工程细节**:
- 表里的 `year` / `week` 列来自 **Panoply 表本身的字段**(不是 BI 派生)
- 这意味着 Panoply 上游已经把 `day → year + week` 物化到表里
- 顶部时间滑块用 `day` + BI 工具自动派生 vs 表格用 Panoply 原生 `year/week`,这是**两套时间系统并行**
- 边界周(跨年周如 2023-W52)两套系统的口径可能不一致 — 详见 §5.1.4 洞察 #2

---

### 5.1.3 数据源追溯

整个 page 的所有字段 100% 来自 **同一张表**:`Style_selling_df`(行级 fact)。

字段血缘(参考 `legacy_panoply_etl.md` §2.4):

| Style_selling_df 字段 | 上游来源 | 关键 join 逻辑 |
|---|---|---|
| `day` / `year` / `week` | Shopify `order.processed_at`(UTC → EST 时区转换)| `processed_at - 5h` |
| `channelgrouping` | GA4 `ga4_test`(归因)| **transactionId 三路兜底 join**:`checkout_id` / `order.id` / `order.name` |
| `quantity` | Shopify `order_line_items.quantity` | 行级粒度 |
| `style` (vend_id) | ERS `mysql_ers.vend_id` | **SKU 主键 + item_description 兜底**双路降级匹配 |
| `Item_description` | ERS `mysql_ers.item_description` | 同上 |
| `season` | ERS `mysql_ers.season` | 同上 |

**结论**:这一个 page 用了销售归因 pipeline 的**全部 join 链** — 包括 §2.3 的两个核心 trick(GA4 三路兜底 + ERS 双路降级)。这两个 trick 是本项目的关键工程亮点。

---

### 5.1.4 关键洞察

#### 洞察 #1:Conformed Fact 服务多角色 — Kimball 维度建模的活样本

**现象**:同一个 fact(`Style_selling_df`),通过不同 slicer + 不同视角,服务 buyer / marketing / merchandiser 三种完全不同的决策场景。

**意义**:这正是 Kimball "conformed fact + 多种 query pattern" 的教科书案例 — 不为不同角色做"专表",而是一个 fact 通过维度切片满足所有需求。

**新平台策略**:
- 行级 fact `dwd.fact_orders_line` 保持单一定义
- 不做角色专表(避免数据冗余 + 口径漂移)
- DWS 层针对热点查询做预聚合(`dws.style_channel_weekly`),但底层一致

#### 洞察 #2:BI 工具派生时间层级 vs 数据源原生时间字段 — 口径不一致风险

**现象**:同一个 page 上,**顶部时间滑块用 BI 工具自动派生的 year/week**(从 `day` 字段派生),**右边矩阵表用 Panoply 原生 `year`/`week` 字段**(上游 ETL 计算的)。

**风险**:
- 跨年周(e.g. 2023-12-31 这周横跨 2023 / 2024)BI 工具自动派生 vs Panoply 计算可能用不同的"周首日"规则(Sunday vs Monday)、不同的"年第几周"算法(ISO 8601 vs Excel WEEKNUM)
- 同一个用户在同一个 page 上看到的数字可能因为筛选路径不同而对不上 — 经典的"两套口径"问题

**新平台解决方案**:
- 用统一的 `dim_date`(单一 source of truth)
- 在 dim 表里固化 `iso_year` / `iso_week` 字段
- 所有时间维度查询都走 dim,杜绝 BI 工具派生

#### 洞察 #3:行级粒度的不可替代性

**现象**:这个 page 需要从 style 层下钻到 Item_description(SKU 级)的销量明细。

**意义**:证明 fact 必须是**行级粒度**,不能用订单级 fact 替代 — 验证了 `legacy_panoply_etl.md §2.3 解法 #4`(双粒度并行建模)的设计正确性。

**新平台策略**:保留 `dwd.fact_orders_line`(行级 fact),不能用 `dwd.fact_orders` 替代这个 page 的需求。

---

### 5.1.5 新平台对应方案

#### Fact / Dim 字段映射

| 旧(Panoply `Style_selling_df`)| 新(Databricks Lakehouse)| 类型 | 备注 |
|---|---|---|---|
| `day` | `dim_date.date_key` | conformed dim | 通过 fact 表的 date_key 关联 |
| `year` / `week` | `dim_date.iso_year` / `dim_date.iso_week` | conformed dim | 统一 ISO 8601,不在 fact 表重复 |
| `channelgrouping` | `dim_channel.channel_name` | conformed dim | **数据源从 GA4 迁移到 TW**,见 §5.1.6 |
| `quantity` | `dwd.fact_orders_line.quantity` | fact measure | 行级 |
| `style` | `dim_product.vend_id` | conformed dim | SCD2 管理 |
| `Item_description` | `dim_product.item_description` | conformed dim | SCD2 管理 |
| `season` | `dim_product.season` | conformed dim | SCD2 管理 |

#### 物理查询路径

```
Web Portal (Next.js)
    ↓ 调用
FastAPI Metrics Service
    ↓ 加载 YAML 指标定义
Metric Layer (YAML DSL)
    ↓ 生成 SQL
Databricks SQL Warehouse
    ↓ 执行
SELECT
    d.iso_year, d.iso_week,
    p.vend_id, p.item_description,
    c.channel_name,
    SUM(f.quantity) AS quantity
FROM dwd.fact_orders_line f
JOIN dim_date d ON f.date_key = d.date_key
JOIN dim_product p ON f.product_key = p.product_key
JOIN dim_channel c ON f.channel_key = c.channel_key
WHERE d.date_key BETWEEN ? AND ?
  AND c.channel_name IN (?)
  AND p.season IN (?)
  AND p.vend_id IN (?)
GROUP BY 1,2,3,4,5
```

#### 待加入 metric_layer 的 YAML 指标

```yaml
# metrics/quantity_by_style_channel_week.yaml
name: quantity_by_style_channel_week
version: 1
description: "按 style × channel × week 维度的销量(件数),支持 Style-channel (quantity) page"
unit: count
grain:
  - iso_year
  - iso_week
  - vend_id
  - channel_name
optional_dims:
  - item_description
  - season
source_fact: dwd.fact_orders_line
measure: SUM(quantity)
filters:
  required:
    - date_range
  optional:
    - channel_name
    - season
    - vend_id
owner: sia
changelog:
  - v1 (2026-05-18): Initial definition, migrated from legacy Style_selling_df
```

---

### 5.1.6 Channel 口径迁移影响(GA4 → TW)

⚠️ **这是 page 迁移的最大变量**。原 page 的 `channelgrouping` 来自 GA4,新平台改用 TW。

**初步对照表**(待 stakeholder + Cal 对齐):

| GA4 channel(旧)| TW channel(新)| 含义 |
|---|---|---|
| Email | `klaviyo` / `attentive` | 邮件 / SMS 营销 |
| Paid Search | `google-ads` | 付费搜索 |
| Organic Search | `direct` 或 `organic_and_social` | 自然搜索(TW 无独立分类)|
| Paid Social | `meta` | 付费社交 |
| Affiliates | `impact` | 联盟营销 |
| Direct / None | `direct` | 直接流量 |
| Cross-network | (TW 无对应)| GA4 特有 |
| Organic Video | `bing` / `organic_and_social` | 自然视频 |

🚩 **关键约束**:TW channel 数据自 **2025-07-01**(TW 接入日)起即可用 — 跨源订单 match 99.9%+ 自 2025-07 起(见 §6 Issue #2),`attribution_order_click` 自 2025-07 起亦有充足渠道数据(2026-06 复核)。更早历史(2023-07 至 2025-06)兜底用 GA4 channel,新平台双口径并存以保持连续性。

> 〔更正 2026-06〕本节早前写作"TW channel 仅从 2025-09 起完整",经复核无数据支撑,且与本文档 §3.1(TW 起始日 2025-07-01)、§6 Issue #2(7 月起 match 99.9%+)矛盾,已更正为 2025-07。

**新平台解决方案**(已在 `legacy_panoply_etl.md §10 决策 #3` 锁定):
- 提供**双口径映射表**,在 portal 可切换
- 默认 TW channel(更结构化、与广告投放对齐)
- 历史段(2025-08 前)兜底用 GA4 channel
- 在 `dim_channel` 表里同时保留 `tw_channel_name` 和 `ga4_channel_name`,FastAPI 服务层按用户选择切换

---

### 5.1.7 待 stakeholder 对齐的口径决策

收集到 §10 待对齐清单(等 §5 全部完成后一次性问 stakeholder):

| # | 决策点 | Sia 建议 |
|---|---|---|
| A | Channel 口径迁移过渡方案(参见 §5.1.6)| 双口径并行,默认 TW |
| B | "Quantity" 是否要排除 refund / replacement?(旧 `Style_selling_df` 已经在 `shopify_orders_order2` 阶段排除了)| 新平台**保留全部订单**,加 `is_refunded` / `is_replaced` flag,前端默认显示 net quantity,可切换看 gross |
| C | Page 是否扩展到月度 / 季度粒度?| 是 — 用 `dim_date` 后零成本支持 |

---

### 5.1.8 §5.1 完成检查清单

- [x] 识别全部 4 个 visual
- [x] 确认数据来源 100% 来自 `Style_selling_df`
- [x] 隐式过滤器审计(无)
- [x] 3 个关键洞察(conformed fact / 时间口径风险 / 行级粒度必要性)
- [x] 完整的旧 → 新字段映射表
- [x] 物理查询路径示例
- [x] YAML 指标定义草稿
- [x] Channel 口径迁移影响分析
- [x] 收集口径决策点,待 §5 全部完成后找 stakeholder 对齐

---

## 5.2 Page: (TBD - 下一个)

(待补充)


---

## 6. Open Issues

在数据接入阶段,通过系统性验证识别出多个数据质量问题。本章节按"问题 → 根因 → 影响 → 状态"四段式记录,作为项目数据治理的事实档案。

---

### Issue #1: Fivetran Shopify Connector 误连至另一品牌的 store

| 项目 | 详情 |
|---|---|
| **发现日期** | 2026-05-05 |
| **状态** | ✅ 已解决(2026-05-13)|
| **严重程度** | 🔴 Critical(完全阻塞跨源建模)|

**现象**:
- Schema 名为 `analytics_catalog.shopify_raw`,内容却是**另一个姊妹品牌(a sister brand)** 的订单
- 订单中 100% `order_status_url` 指向该姊妹品牌的域名,0 命中 the retailer 的域名
- 99% `order_line.vendor` = 该姊妹品牌(非 the retailer)
- 订单号格式属该姊妹品牌体系,非 the retailer 体系
- 与 TW(the retailer 数据)跨源 join 在同时间窗口下匹配率 0%

**根因**:Fivetran connector 配置时连接到了一个姊妹品牌的 Shopify store,而非 the retailer 的 store。Schema 命名与实际数据来源不一致。

**影响**:如未及时发现,所有下游建模将基于错误的业务主体数据,导致整个 dashboard 反映错误品牌的业务情况。

**解决方案**:
- 通过 5 维证据(domain / vendor / order ID 格式 / 跨源 join / 关键词搜索)定位问题
- 跨团队协调 Fivetran connector owner 重新配置至 the retailer 的 Shopify store
- 配置完成后通过 source reconciliation(vs Panoply)验证数据完整性,8 日累计差异 0.5%,低于 1% 阈值

---

### Issue #2: TW `attribution_order` 历史数据 backfill 阶段性缺失

| 项目 | 详情 |
|---|---|
| **发现日期** | 2026-05-05(初次)/ 2026-05-13(细节)|
| **状态** | 🟡 部分解决,1-2 月 backfill 进行中 |
| **严重程度** | 🟡 High(阻塞 Phase 2B/3 真实建模,不阻塞文档与设计工作)|

**现象**:
- 初始接入时(5/5):`attribution_order` 仅有 9 天数据(2026-04-28 至今)
- 首次 backfill 后(5/13):数据回溯至 2025-07-01,但 2025-11 至 2026-02 旺季月份订单量比相邻月份骤降 95%+
- 二次 backfill 后(5/14):2025-10 至 2025-12 月数据补齐,但 2026-01/02 仍存在大缺口

**当前 match rate 状态(跨源 vs Shopify)**:

| 月份 | Shopify 订单 | TW 匹配订单 | Match Rate | 状态 |
|---|---|---|---|---|
| 2025-07 至 10 | ~700K | ~700K | 99.95% | ✅ |
| 2025-11 | 383K | 383K | 99.95% | ✅ |
| 2025-12 | 428K | 394K | 92.06% | ✅ |
| **2026-01** | **329K** | **73K** | **22.17%** | 🚩 |
| **2026-02** | **172K** | **46K** | **26.73%** | 🚩 |
| 2026-03 至 05 | ~482K | ~482K | 99.98% | ✅ |

**根因**:Custom TW pipeline 在 backfill 过程中分批同步,部分月份未被某一批次的时间窗口覆盖。这是 backfill 实施细节问题,不是 TW 系统本身缺数据(已通过 TW Dashboard 直接验证 the retailer 数据从 2025-07-01 起完整可用)。

**影响**:
- 阻塞 Phase 2B/3 的真实数仓建模(fact 表 1-2 月会缺数据)
- 不阻塞 Track 1 文档撰写、Track 2 框架级设计、Track 3 DQ 框架(已完成)

**解决方案**:
- 已向 TW pipeline owner 提交 backfill 请求(含详细缺口数据)
- 定义可量化的"数据完整"判定标准:**跨源 month-level match rate ≥ 90%**
- 每日跑完整性测试 SQL 跟踪修复进度(见 Appendix A.2)

---

### Issue #3: 跨源 Match Rate 基线初期判断失误(已修正)

| 项目 | 详情 |
|---|---|
| **发现日期** | 2026-05-13 |
| **状态** | ✅ 已修正认知 |
| **严重程度** | 🟢 Low(认知问题,不影响数据本身)|

**现象**:5/5 首次跨源 join 测试得到 44% match rate,初期被误判为"DTC 行业归因覆盖率合理基线(剩余 56% 为 direct/unattributed 自然流量)"。

**根因**:5/5 测试时 TW 那侧仅有 7-9 天数据,绝大部分 Shopify 历史订单本就无 TW 数据可匹配。**44% 是数据不完整状态下的伪基线,不是真实业务基线**。

**修正认知**:基于完整数据(TW backfill 后)重新测试,健康月份 match rate 实际为 **92-99.98%**。TW 实际追踪**所有 Shopify 订单**,包括 direct/unattributed 流量(channel 字段标记为 'direct'),而非"只追踪有归因的订单"。

**经验教训**:**数据基线必须在数据稳定后再测**。中间状态测出的基线会误导后续判断。

---

### Issue #4: TW `federated_catalog` 命名误导

| 项目 | 详情 |
|---|---|
| **发现日期** | 2026-05-05 |
| **状态** | ℹ️ 已澄清,无需修改 |
| **严重程度** | 🟢 Informational |

**现象**:catalog 名为 `federated_catalog`,字面上像是 Databricks 的 Lakehouse Federation(联邦查询外部数据库),实际上是 custom pipeline 写入的 managed table。

**根因**:命名继承自历史架构决策,未与实际接入方式同步更新。

**影响**:无技术影响。仅影响新接入工程师的初期理解,可能误以为是 federated query 场景。

**解决方案**:在本文档中明确说明实际接入方式为 custom pipeline,避免后续误解。

---

## 7. Appendix

### A.1 Source Reconciliation 验证 SQL(Shopify Databricks vs Panoply)

用于验证 Fivetran 同步完整性,推荐每月跑一次。

```sql
-- Databricks Shopify 日订单量(对比 Panoply 同期)
SELECT 
  DATE(created_at) AS order_date,
  COUNT(*) AS databricks_orders
FROM analytics_catalog.shopify_raw.order
WHERE created_at >= DATE_SUB(CURRENT_TIMESTAMP(), 7)
GROUP BY 1
ORDER BY 1;
```

**判定标准**:累计差异 < 1% 视为健康。每日差异 ±3% 由 UTC vs EST 时区边界效应导致,属正常。

---

### A.2 TW 数据完整性测试 SQL(返回空 = ready)

用于判断 TW 是否完成 backfill,可以启动 Phase 2B/3。

```sql
SELECT 
  DATE_TRUNC('month', s.created_at) AS month,
  ROUND(
    COUNT(DISTINCT CASE WHEN t._triple_whale_order_id IS NOT NULL THEN s.id END) * 100.0 
    / COUNT(DISTINCT s.id), 2
  ) AS match_rate_pct
FROM analytics_catalog.shopify_raw.order s
LEFT JOIN federated_catalog.triple_whale.attribution_order t
  ON CAST(s.id AS STRING) = CAST(t._triple_whale_order_id AS STRING)
WHERE s.created_at >= '2025-07-01' 
  AND s.created_at < CURRENT_DATE()
GROUP BY 1
HAVING match_rate_pct < 90
ORDER BY 1;
```

**判定标准**:返回 0 行 = 所有月份 match rate ≥ 90% = TW 数据完整,可启动数仓建模。

---

### A.3 跨源 Join 关联示例

```sql
-- 标准跨源 join 模板:Shopify 订单 + TW 归因
SELECT 
  s.id           AS shopify_order_id,
  s.name         AS order_name,
  s.total_price  AS shopify_revenue,
  s.created_at,
  t.total_price  AS tw_revenue,
  t._synced_at   AS tw_synced_at
FROM analytics_catalog.shopify_raw.order s
LEFT JOIN federated_catalog.triple_whale.attribution_order t
  ON CAST(s.id AS STRING) = CAST(t._triple_whale_order_id AS STRING)
WHERE s.created_at >= '2026-01-01';
```

**注意点**:
- `s.id` 是 BIGINT,`t._triple_whale_order_id` 是 STRING,join 时需要 cast
- LEFT JOIN 保留所有 Shopify 订单,即使没有 TW 归因
- 健康月份 match rate ≥ 92%

---

### A.4 多触点归因示例查询

```sql
-- 查询某订单的完整营销旅程
SELECT 
  position,
  source,
  campaign_id,
  click_date,
  attribution_model
FROM federated_catalog.triple_whale.attribution_order_click
WHERE _triple_whale_order_id = '7137654571097'
  AND attribution_model = 'linear'
ORDER BY position;
```

---

### A.5 数据质量监控关键指标

为 DQ 框架(`metrics-service/data_quality/`)预设的检查清单:

| 检查项 | 数据源 | 期望阈值 |
|---|---|---|
| Shopify `order.id` not null | shopify_orders | 100% |
| Shopify `order.id` unique | shopify_orders | 100% |
| Shopify `order.total_price` ≥ 0 | shopify_orders | 100% |
| Shopify `_fivetran_synced` freshness | shopify_orders | ≤ 48 小时 |
| TW `_triple_whale_order_id` not null | attribution_order | 100% |
| TW `_triple_whale_order_id` unique | attribution_order | 100% |
| TW `_synced_at` freshness | attribution_order | ≤ 48 小时 |
| 跨源 monthly match rate | join | ≥ 90% |

详见 `metrics-service/data_quality/configs/`。
