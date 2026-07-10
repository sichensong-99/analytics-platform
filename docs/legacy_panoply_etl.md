# Legacy Panoply ETL — Reverse Engineering Documentation

> **Purpose**: 系统性反向工程 Sia 过去 2 年在 Panoply 构建的全部 query model 体系,作为新平台(Databricks)数仓建模的需求圣经。
>
> **Why this document matters**:
> Phase 2B/3 数仓建模的**业务口径需求输入**(没有这份文档,fact/dim 设计无据可依)
>
> **Last Updated**: 2026-05-15
> **Status**: 🟢 Living document — 进度 95%,核心业务域已全部覆盖,剩余 5% 在 Section 5 PBI 映射阶段边做边补

---

## 0. Executive Summary

### 0.1 过去 Panoply 体系全景

Sia 在 Panoply 上构建了一套支撑 **20+ page PBI report** 的数据 pipeline,覆盖 **6 大业务域**,共 **~30 张 query model 表**,服务于:
- 销售归因(Style × Channel × Time)
- 退货分析(Refund Analysis with Root Cause Attribution)
- 替换分析(Replacement Analysis)
- 运费成本(Freight Cost)
- 订单篮子行为(Basket Behavior Analytics)
- 产品主数据整合(Product Master with Fallback Matching)

### 0.2 工程亮点速览

| # | 亮点 | 业务域 | 难度 |
|---|---|---|---|
| 1 | GA4 transactionId **多键三路 join** 兜底 | 销售归因 | 🌟🌟🌟 |
| 2 | sku → item_description **双路径降级匹配** | 产品维度 | 🌟🌟🌟 |
| 3 | **Schema Evolution 兼容**(老 tags + 新 metafield 双路径并行) | 退货/替换 | 🌟🌟🌟🌟 |
| 4 | 20+ CASE WHEN 的**业务规则标签分类引擎** | 退货/替换 | 🌟🌟 |
| 5 | **Responsibility 归因模型**(WAREHOUSE / SHIPPING / MERCHANT) | 退货/替换 | 🌟🌟🌟 |
| 6 | REGEXP_EXTRACT **从自由文本反推 original_order** | 替换分析 | 🌟🌟🌟 |
| 7 | `PERCENTILE_CONT` **日级中位数**(对抗长尾偏倚) | 订单行为 | 🌟🌟🌟 |
| 8 | GA4 `__updatetime` **最新版本去重**(SCD pattern) | 数据清洗 | 🌟🌟 |
| 9 | 手工 monthly CSV(freight)**整合到 Lakehouse** | 运费 | 🌟🌟 |
| 10 | 时区统一处理(`processed_at - 5h`)| 通用 | 🌟 |
| 11 | **双粒度并行建模**(行级 + 订单级 fact)— Kimball grain 原则 ⭐ | 销售归因 | 🌟🌟🌟🌟 |
| 12 | **时间分片数据源切换**(GA UA → GA4 平滑迁移)| 销售归因 | 🌟🌟🌟 |
| 13 | **BI 逻辑下沉数据层**(DAX → conformed dim)⭐ | 架构演进 | 🌟🌟🌟 |
| 14 | **Anti-bulk-bias 过滤**（`total_order_qty<=30` 排 B2B 大单，避免污染 retail 行为分析）| 销售归因/订单行为 | 🌟🌟 |
| 15 | **Customer Cohort 分类**（`orders_count` 权威累计 vs 库内实抓单数 之差，识别接入前历史客户，避免老客误判 first-time；对增量同步缺早期数据稳健）⭐ | 客户分析 | 🌟🌟🌟🌟 |


### 0.3 体量规模

| 维度 | 数字 |
|---|---|
| Query model 表数量 | ~30 张 |
| 数据源 | Shopify + GA4 + ERS(产品主数据)+ 月度运费 CSV |
| 服务的 PBI report 页面数 | 20+ pages |
| 业务域 | 6 个 |
| Pipeline 历史 | 2-3 年迭代,见证了 Shopify metafield 上线后的 schema evolution |

---

## 1. Data Lineage 全景图

```
┌──────────────────────────────────────────────────────────────────────┐
│                          原始采集层(ODS-equivalent)                  │
├──────────────────────────────────────────────────────────────────────┤
│  Shopify(Panoply auto-sync):                                        │
│    - shopify_orders_order                                            │
│    - shopify_orders_order_line_items                                 │
│    - shopify_orders_order_customer                                   │
│    - shopify_orders_order_fulfillments                               │
│    - shopify_orders_order_refunds                                    │
│    - shopify_orders_order_refunds_transactions                       │
│    - shopify_orders_order_refunds_refund_line_items                  │
│                                                                      │
│  GA4(Panoply auto-sync):                                            │
│    - ga4_test                                                        │
│                                                                      │
│  ERS(MySQL 同步过来):                                                │
│    - mysql_ers (产品主数据:vend_id/style/group/season/gender/class) │
│                                                                      │
│  Freight(月度人工上传):                                              │
│    - mysql_freight_raw_data                                          │
└──────────────────────────────────────────────────────────────────────┘
                                  ↓
┌──────────────────────────────────────────────────────────────────────┐
│                          清洗去重层(DWD-equivalent)                  │
├──────────────────────────────────────────────────────────────────────┤
│  - ga4_test2(按 date + __updatetime 取最新版本)                     │
│  - ga4(date >= 2023-07-01,作为 GA4 启用日)                         │
└──────────────────────────────────────────────────────────────────────┘
                                  ↓
┌──────────────────────────────────────────────────────────────────────┐
│                        业务域 1: 销售归因 Pipeline                    │
├──────────────────────────────────────────────────────────────────────┤
│  shopify_orders_order2                                               │
│    = order 排除 (refund + replacement + EXC + Returnly)              │
│      ↓                                                                │
│  Shopify_orders_items_GA4_for_dollars                                │
│    = order2 ⋈ line_items ⋈ ga4(三路 transactionId 兜底 join)        │
│      ↓                                                                │
│  Style_selling_df_GA4_for_dollarsNEW                                 │
│    = 加 ERS 产品维度(sku 主路径 + item_description 兜底降级匹配)    │
│      ↓                                                                │
│  Style_selling_dfNEW                                                 │
│    = GA UA 版本 UNION ALL GA4 版本(2023/7/1 后只保留 GA4)          │
│      ↓                                                                │
│  PBI: Style_selling_df → 20+ pages 的核心数据源                     │
└──────────────────────────────────────────────────────────────────────┘
                                  ↓
┌──────────────────────────────────────────────────────────────────────┐
│                  业务域 2: 退货 Pipeline(双路径并行)                 │
├──────────────────────────────────────────────────────────────────────┤
│  路径 A(老 tags):                                                   │
│    refund1(基于 order.tags LIKE '%refund%')                         │
│      → refund1_new_extra(加 20+ CASE WHEN tag_category + Resp.)     │
│                                                                      │
│  路径 B(新 metafield):                                              │
│    refund1_metafield(基于 order.replace_refund='["Refund"]')        │
│      → refund1_metafield_new(加 metafield-based tag_category)       │
│                                                                      │
│  合并:                                                                │
│    refund1_news = refund1_metafield_new UNION ALL refund1_new_extra │
│                                                                      │
│  下游:                                                                │
│    refund4 = refund1_news ⋈ order_refunds_refund_line_items         │
│           (退货 → 行级 SKU 粒度)                                    │
└──────────────────────────────────────────────────────────────────────┘
                                  ↓
┌──────────────────────────────────────────────────────────────────────┐
│                  业务域 3: 替换 Pipeline(双路径并行)                 │
├──────────────────────────────────────────────────────────────────────┤
│  路径 A(老 note 正则):                                              │
│    replacement_orders2(REGEXP_EXTRACT note 找 original_order)       │
│      → replacement1 ⋈ customer ⋈ subtotal                           │
│      → Replacements ⋈ freight ⋈ replacement_count                   │
│      → Replacements_new_extra(20+ CASE WHEN)                         │
│                                                                      │
│  路径 B(新 metafield):                                              │
│    replacement_orders3(用 original_order_if_replaced_ + replace_refund)│
│      → replacement3 → Replacements3                                  │
│      → Replacements_new_metafield(不同的 CASE WHEN 逻辑)             │
│                                                                      │
│  合并:                                                                │
│    Replacements_news = Replacements_new_extra UNION ALL              │
│                       Replacements_new_metafield                     │
└──────────────────────────────────────────────────────────────────────┘
                                  ↓
┌──────────────────────────────────────────────────────────────────────┐
│                       业务域 4: 运费 Pipeline                         │
├──────────────────────────────────────────────────────────────────────┤
│  Freight_orders2_new(replace_refund IS NULL 的常规订单)             │
│  Freight_orders3(replace_refund='["Replace"]' 的替换订单)           │
│  → 都用 order.name ⋈ mysql_freight_raw_data 关联                    │
└──────────────────────────────────────────────────────────────────────┘
                                  ↓
┌──────────────────────────────────────────────────────────────────────┐
│                  业务域 5: 订单篮子行为 Pipeline                      │
├──────────────────────────────────────────────────────────────────────┤
│  orders_product(line-level,排除替换 + 退货)                         │
│    → orders_product_dump(加 ERS master_style,双路径降级匹配)        │
│    → orders_product_dump_day(订单级 → 日级聚合,4 个篮子指标)       │
│  orders_median_price(PERCENTILE_CONT 日级中位数)                    │
│  合并:orders_product_dump_day ⋈ orders_median_price                 │
└──────────────────────────────────────────────────────────────────────┘
                                  ↓
┌──────────────────────────────────────────────────────────────────────┐
│                  业务域 6: 产品主数据 + Basket                        │
├──────────────────────────────────────────────────────────────────────┤
│  mysql_ers(独立维度表)                                              │
│  Basket_orders(订单 × 行 × 产品 × 客户的扁平视图,供 PBI 直接消费)  │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 2. 业务域 1: 销售归因(Sales × Attribution)

### 2.1 业务问题

「**每个 style 在每个营销渠道、每周卖了多少件、贡献多少美金?**」

这是 PBI 整套 report 的核心问题,服务于 **ecom 团队所有角色**(buyer / marketing / merchandiser),每个角色用同一份数据做不同决策:
- **Buyer**:基于 style × week × quantity 趋势,决定下季度备货 SKU 与数量
- **Marketing**:基于 channel × week × quantity 趋势,评估渠道效果、调投放预算
- **Merchandiser**:基于 style × channel 交叉,决定哪些款式适合哪些渠道推广

⭐ **设计含义**(对新平台的影响):
- **同一份 fact 表服务多角色**,这正是 Kimball 维度建模的核心价值(conformed fact + 多种 query pattern)
- 新平台必须支持**多种切片视角**(by style / by channel / by week / 三维交叉),不能为某一角色定制专表
- 不需要做"权限分级"——所有 ecom 组成员都能看到全量数据

### 2.2 工程挑战

1. **数据源跨平台**:订单在 Shopify,归因在 GA4,需要 join 但 GA4 的 transactionId 字段值不稳定(可能是 `checkout_id` / `order.id` / `order.name` 三种之一)
2. **产品维度缺失**:Shopify 的 line_items 没有 style / group / season 等业务维度,要 join 外部 ERS 主数据,但 sku 不一定能匹配上
3. **历史数据归因源不同**:2023-07-01 前是 GA UA,之后是 GA4,要兼容
4. **要排除 noise**:refund / replacement / exchange 订单不能计入销售

### 2.3 工程解法 ⭐⭐⭐

#### 解法 #1: GA4 transactionId **多键三路 join 兜底**

```sql
-- 三路 UNION DISTINCT,匹配上一路即可
路径 A: ga4.transactionid (数字) ↔ shopify.order.checkout_id
路径 B: ga4.transactionid (数字) ↔ shopify.order.id
路径 C: ga4.transactionid (#开头)↔ shopify.order.name
```

**工程意义**:GA4 的 transactionId 是前端埋点上报的,开发者可能填 checkout_id / order_id / order_name 任一种,数据工程必须**兜底**所有可能。这叫 **Multi-key Resolution**,处理上游数据契约松散问题。

#### 解法 #2: sku → item_description **双路径降级匹配**

```sql
-- 先用 sku 主路径
LEFT JOIN ers ON line_items.sku = ers.unique_identifier
-- sku 匹配失败的(vend_id IS NULL),改用 item_description 兜底
LEFT JOIN ers ON line_items.title = ers.item_description
-- UNION DISTINCT 合并
```

**工程意义**:**Graceful Degradation in Entity Resolution**,主键失效自动降级到次键。这是数据治理高阶技巧。

#### 解法 #3: 订单清洗 — `shopify_orders_order2`

```sql
WHERE name NOT IN (Replacements_news)     -- 排除替换
  AND name NOT IN (refund1_news)           -- 排除退款
  AND name NOT LIKE '%EXC%'                -- 排除 exchange
  AND lower(tags) NOT LIKE '%returnly%'    -- 排除 Returnly 处理
```

**工程意义**:Panoply 没有原生 return 表,所有"是否退货"逻辑都靠 `tags / note / replace_refund` 字段反推,这是**业务规则硬编码**的反模式,但在受限平台上是不得已的解法。

#### 解法 #4: **双粒度并行建模**(Multi-grain Modeling)⭐⭐⭐⭐

Sia 实际上做了**两套并行的归因 pipeline**,服务不同分析粒度:

```
┌────────────────────────────────────────────────────────────┐
│ 体系 A — 行级归因(line-item granularity)                  │
│   表:Shopify_orders_items_GA4_for_dollars                   │
│        Style_selling_df_GA4_for_dollarsNEW                 │
│        Style_selling_dfNEW                                  │
│   用途:Style × Channel 的件数/销量(需要 SKU 维度)         │
│   join 链:order ⋈ line ⋈ ga4 ⋈ ers(主路)⋈ ers(降级)    │
│   行数级别:~5M 行 / 年                                     │
│   性能:重                                                  │
└────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────┐
│ 体系 B — 订单级归因(order-level granularity)              │
│   表:Shopify_orders_items_GA4_for_dollars2                  │
│        (在 PBI 里 UNION 后叫 CombinedTable)                 │
│   用途:Channel × Date 的订单金额分析(不需要 SKU 维度)     │
│   join 链:order ⋈ ga4(精简版,无 line / ers)               │
│   行数级别:~1M 行 / 年                                     │
│   性能:轻                                                  │
└────────────────────────────────────────────────────────────┘
```

**工程意义**:这是 **Kimball 维度建模"don't pre-join across grains"原则的实际应用**。
- 行级 fact 用于 SKU 维度分析(慢但全)
- 订单级 fact 用于 channel 维度分析(快但粗)
- 两个 fact 各自服务最适合的查询模式,**避免大宽表反模式**

#### 解法 #5: **时间分片数据源切换**(Temporal Data Source Switching)⭐⭐⭐

GA UA 在 2023-07-01 停止 → GA4 接替,但 Sia 不是 "Big Bang" 切换,而是:

```sql
-- _dollars2 :  WHERE day <  '2023-06-29' → 走 GA UA support 表
-- _dollars2 :  WHERE day >= '2023-06-29' → 走 GA4 support 表
-- PBI 里通过 DAX UNION 拼接两段时间窗口
```

**工程意义**:**Temporal Data Source Switching** 是处理 SaaS 平台迁移(GA UA → GA4)、避免历史数据断裂的标准模式。新平台已经决定砍掉 2023/7/1 前数据,所以这个模式不再需要。

### 2.4 涉及表清单(双粒度体系)

**体系 A — 行级归因 pipeline**:

| 表名 | 类型 | 角色 |
|---|---|---|
| `shopify_orders_order` | ODS | 原始订单 |
| `shopify_orders_order_line_items` | ODS | 订单行 |
| `ga4_test` / `ga4_test2` / `ga4` | ODS / 清洗 | GA4 归因(`__updatetime` 去重)|
| `mysql_ers` | 维度 | 产品主数据 |
| `shopify_orders_order2` | 清洗 | 排除 refund/replacement/EXC |
| `Shopify_orders_items_GA4_for_dollars` | 中间 | order ⋈ line ⋈ ga4(三路 join)|
| `Style_selling_df_GA4_for_dollarsNEW` | 中间 | 加 ERS 维度(双路降级)|
| `Style_selling_dfNEW` | 终表 | UA + GA4 UNION ALL,PBI 直接消费 |

**体系 B — 订单级归因 pipeline**:

| 表名 | 类型 | 角色 |
|---|---|---|
| `Shopify_orders_items_GA4_for_dollars2_support` | 中间 | GA4 三路 join 出 order ↔ channel/campaign |
| `Shopify_orders_items_GA_for_dollars2_support` | 中间 | GA UA 同上(2023/7/1 前)|
| `Shopify_orders_items_GA4_for_dollars2` | 终表 | order ⋈ support,日级 GA4 段 |
| `Shopify_orders_items_GA_for_dollars2` | 终表 | order ⋈ support,日级 GA UA 段(2023/7/1 前)|
| `CombinedTable`(DAX 层)| PBI 内 | 上面两个的 UNION |

### 2.5 PBI 消费

- 行级:`Style_selling_df`(在 PBI 里 rename 自 Panoply 的 `Style_selling_dfNEW`)
- 订单级:`CombinedTable`(DAX 在 PBI 里 UNION `Shopify_orders_items_GA_for_dollars2` + `Shopify_orders_items_GA4_for_dollars2`)

### 2.6 新平台演进方向

| 旧方案 | 新方案 |
|---|---|
| GA4 三路兜底 join | TW 直接提供 `_triple_whale_order_id` → 单键关联 |
| sku/item_description 双路降级 | ERS 主数据已上传到 Databricks,建独立 `dim_product`,SCD2 管理 |
| 排除 refund/replacement(硬过滤)| 保留全部订单,加 `is_refunded` / `is_replaced` flag |
| `shopify_orders_order2`(子表)| 不再需要,改为查询时按 flag 过滤 |
| 2023/7/1 前的 UA 路径 + 时间分片 | **整条砍掉**(项目数据起点 = 2023-07-01)|
| 行级 `Style_selling_dfNEW` | `dwd.fact_orders_line`(SKU 粒度 fact)|
| 订单级 `CombinedTable` | `dwd.fact_orders`(订单粒度 fact)|
| 行级 + 订单级两套 pipeline | **保留双粒度设计**,在新平台用 Kimball 规范化命名 |

---

## 3. 业务域 2: 退货分析(Refund Analysis)

### 3.1 业务问题

「**退货的原因是什么?谁的责任?(Warehouse / Shipping Carrier / the retailer)**」

服务于:
- 仓库改善流程(missing item / wrong item 比例)
- Shipping carrier 谈判(damage / lost in transit 比例)
- 财务对账(refund 金额、freight cost 损失)

### 3.2 工程挑战

1. **Shopify 没给独立 refund reason 字段**,只能从 `tags`(自由文本)反推
2. **Shopify 后来上了 metafield**(`replace_refund`、`order_issue`),旧数据用 tags,新数据用 metafield,**必须同时兼容**
3. **退货金额、运费、产品成本要 join 多张表才能得到完整图景**
4. **退货 SKU 行级粒度**需要进一步 join `order_refunds_refund_line_items`

### 3.3 工程解法 ⭐⭐⭐⭐

#### 解法 #1: **Schema Evolution 兼容**(老 tags + 新 metafield 双路径并行)⭐

```
路径 A(老 tags):
  refund1 → refund1_new_extra
  过滤:tags LIKE '%refund%' AND tags NOT LIKE '%returnly%'
  分类:20+ CASE WHEN on UPPER(tags)

路径 B(新 metafield):
  refund1_metafield → refund1_metafield_new
  过滤:replace_refund = '["Refund"]'
  分类:基于 order_issue 字段(更结构化)

合并:
  refund1_news = UNION ALL of A + B
```

**工程意义**:**Schema Evolution Backward Compatibility**。当上游 SaaS 平台演进 schema 时,数据工程的标准做法是**新旧并行,逐步迁移**,而不是 "Big Bang" 切换。这是数据平台演进的标准思路。

#### 解法 #2: **20+ CASE WHEN 业务规则标签分类引擎**

```sql
CASE 
  WHEN UPPER(tags) LIKE '%DA%MA%D ITEM%' THEN 'Shipping Damage'
  WHEN UPPER(tags) LIKE '%MIS%ING%' THEN 'Missing Item'
  ...(共 18 种 tag_category)
  ELSE 'Other'
END AS tag_category
```

**工程意义**:把**业务专家的领域知识**编码成 SQL 规则,实现自动分类。这是在数据层在数据上"业务化"的关键能力。可在新平台演进为 **YAML driven rule engine** 或独立的 `dim_refund_reason` 表。

#### 解法 #3: **Responsibility 归因模型**

```sql
CASE 
  WHEN tag_category IN ('Missing Item', 'Wrong Item', 'Wrong Order') 
    THEN 'WAREHOUSE'
  WHEN tag_category IN ('Shipping Damage', 'Lost In Transit', 'No Movement', 'Not Received') 
    THEN 'SHIPPING CARRIER'
  ELSE 'THE RETAILER'
END AS Responsibility
```

**工程意义**:把"分类标签"进一步聚合成"责任归属",直接驱动业务决策(找谁谈、改哪个流程)。**数据 → 决策的最后一公里**。

#### 解法 #4: 退货 SKU 行级粒度 — `refund4`

```sql
refund1_news ⋈ order_refunds ⋈ order_refunds_refund_line_items
→ 一笔退货 → N 个退货 SKU 行
```

**工程意义**:从订单级**下钻到 SKU 级**,支持"哪个 style 退货率最高"这类分析。

### 3.4 涉及表清单

| 表名 | 角色 | 注释 |
|---|---|---|
| `shopify_orders_order_refunds` | ODS | Shopify 原生退款主表 |
| `shopify_orders_order_refunds_transactions` | ODS | 退款金额 |
| `shopify_orders_order_refunds_refund_line_items` | ODS | 退货行级 |
| `refund1` | 中间(路径 A)| tags 过滤 |
| `refund1_new_extra` | 中间(路径 A)| 加 tag_category |
| `refund1_metafield` | 中间(路径 B)| metafield 过滤 |
| `refund1_metafield_new` | 中间(路径 B)| 加 tag_category |
| `refund1_news` | 终表 | 合并 A + B |
| `refund4` | 下钻 | 行级退货 |

### 3.5 新平台演进方向

✨ **新平台 Shopify 已经原生有独立 return 表**!
- `analytics_catalog.shopify_raw.return`
- `analytics_catalog.shopify_raw.return_line_item`
- `analytics_catalog.shopify_raw.return_shipping_fee`
- `analytics_catalog.shopify_raw.order_line_refund`

| 旧方案 | 新方案 |
|---|---|
| 从 tags / metafield 反推 | 直接用 `return` / `return_line_item` 原生表 |
| `refund1_news`(20+ CASE WHEN)| `dim_refund_reason`(独立维度表,YAML-driven 维护)|
| `Responsibility` 硬编码 in SQL | `dim_refund_reason.responsibility` 字段 |
| `refund4` 子查询 | `dwd.fact_refund_line`(行级 fact)|

---

## 4. 业务域 3: 替换分析(Replacement Analysis)

### 4.1 业务问题

「**哪些原始订单被替换了?替换原因是什么?替换运费成本多少?**」

替换 ≠ 退货:客户收到商品有问题,MERCHANT 寄一个新的过去,旧的不要退。所以需要**关联原订单和替换订单**。

### 4.2 工程挑战

1. **没有原生 replacement 关联**,要从客服在 `note` 字段写的自由文本里**反推 original_order**(`"OG #12345"` / `"original 12345"` 等不同写法)
2. 同样存在 **Schema Evolution**:后来 Shopify 上了 `original_order_if_replaced_` metafield + `replace_refund` 标记
3. 替换涉及 **2 个订单**(原 + 替换),要关联两边的金额、运费、客户
4. **客户级 replacement_count**(同一客户被替换过几次)需要 self-join

### 4.3 工程解法 ⭐⭐⭐⭐

#### 解法 #1: REGEXP_EXTRACT **从自由文本反推 original_order**

```sql
CONCAT('#', REGEXP_EXTRACT(
  LOWER(note),
  '(?:.*(?:og|orig|nal|orgin|o0riginal).*? ?#?)([0-9]+)',
  1
)) AS original_order
```

加上一堆 noise 排除:
```sql
WHERE note LIKE '%og%' OR note LIKE '%orig%' OR ...
  AND note NOT LIKE '%repla%' AND note NOT LIKE '%replpace%' AND ...
```

**工程意义**:**Text Parsing in SQL**,把"客服自由文本"提取成结构化关联。

#### 解法 #2: 双路径并行(同退货)

```
路径 A(老 note 正则):
  replacement_orders2 → replacement1 → Replacements → Replacements_new_extra

路径 B(新 metafield):
  replacement_orders3 → replacement3 → Replacements3 → Replacements_new_metafield
```

#### 解法 #3: 多重 self-join 关联原订单 / 替换订单 / 客户 / 运费

```sql
Replacements = replacement1 
  ⋈ (original_order → freight)
  ⋈ (replacement_order → freight)
  ⋈ (customer → COUNT(*) AS replacement_count)
  ⋈ (original_order → customer_shipping_paid via Freight_orders2_new)
```

### 4.4 新平台演进方向

✨ **同样,新平台 Shopify 原生 return 表覆盖了 exchange/replacement 场景**(`return.return_type` 字段)。

| 旧方案 | 新方案 |
|---|---|
| REGEXP_EXTRACT 自由文本 | Shopify 原生 `return` 表 + `return_type='EXCHANGE'` |
| Replacements_news(20+ CASE WHEN)| 复用 `dim_refund_reason` |
| 双 freight join(orig + replacement)| `dim_freight` + 双 fact 行 |

---

## 5. 业务域 4: 运费成本(Freight Cost)

### 5.1 业务问题

「**每个订单的运费成本(carrier 收 MERCHANT)vs 客户实付运费 vs 实际承运商和类型**」

### 5.2 工程挑战

1. **运费数据是月度人工 CSV 上传**(`mysql_freight_raw_data`),不是自动同步
2. 一个订单可能在 carrier 那有多笔运费(多个包裹),要 SUM
3. 常规订单 vs 替换订单,运费要分开统计

### 5.3 工程解法

```sql
-- Freight_orders2_new(常规订单,replace_refund IS NULL)
shopify_orders_order ⋈ mysql_freight_raw_data ON order.name = freight.order_id

-- Freight_orders3(替换订单,replace_refund='["Replace"]')
同上,过滤条件不同

-- 关键字段
total_rate            -- carrier 收 MERCHANT 多少钱(成本)
customer_shipping_paid -- 客户在 Shopify 付了多少运费(收入)
carrier_freight       -- CONCAT(carrier_tag, '-', freight_type) 复合维度
```

### 5.4 新平台演进方向

| 旧方案 | 新方案 |
|---|---|
| 月度 CSV 手工上传 | 走 Databricks Auto Loader streaming(自动监听文件落地)⭐ |
| Freight_orders2_new + Freight_orders3 双表 | `dwd.fact_freight`(单表 + `is_replacement` flag)|
| `carrier_freight` 字符串拼接 | `dim_carrier`(carrier_tag + freight_type 维度)|

⭐ **这条线刚好可以接到 Phase 4.5 streaming 模块!**:"月度 CSV → Auto Loader → 自动监听文件落地写入 Delta 表"。

---

## 6. 业务域 5: 订单篮子行为(Basket Behavior Analytics)

### 6.1 业务问题

「**典型订单长什么样?平均一单多少件?多少个 SKU?多少美金?中位数 vs 均值?**」

服务于:
- Marketing 评估营销活动是否推高了篮子大小
- Buyer 评估 bundle 策略

### 6.2 工程挑战

1. **均值受极端值影响**(企业批量订单拉高均值),需要看**中位数**才能反映典型客户行为
2. 需要多个不同粒度的去重统计(SKU 数 / unique SKU / unique master_style)

### 6.3 工程解法 ⭐⭐⭐

#### 解法: `PERCENTILE_CONT` 日级中位数

```sql
WITH daily_order_totals AS (
  SELECT date, name AS order_id, SUM(pre_tax_price) AS total_amount
  FROM orders_product_dump
  GROUP BY date, name
)
SELECT 
  date,
  PERCENTILE_CONT(total_amount, 0.5) OVER (PARTITION BY date) AS median_price
FROM daily_order_totals
```

**工程意义**:**统计正确性 > 简单计算**。讲 `mean vs median` 在长尾分布数据中的差异,体现对统计正确性的把握。

#### 4 个篮子指标

| 指标 | 含义 |
|---|---|
| `Avg_units_per_order` | 平均每单总件数 |
| `Avg_unique_skus_per_order` | 平均每单 SKU 多样性 |
| `Avg_unique_products_per_order` | 平均每单 master_style 多样性 |
| `Avg_order_value` | 平均订单金额(mean)|
| `median_price` | 中位订单金额 ⭐ |

### 6.4 新平台演进方向

直接在 `dwd.fact_orders` 上跑窗口聚合,产出 `dws.daily_basket_behavior` 表。`PERCENTILE_CONT` 思路保留并扩展到 P25 / P75 / P90。

---

## 7. 业务域 6: 产品主数据 + Basket(支撑表)

### 7.1 mysql_ers — 产品主数据

ERS 系统(企业资源系统)的产品主表,通过 MySQL 同步到 Panoply。

| 字段 | 含义 |
|---|---|
| `unique_identifier` | sku 主键 |
| `item_description` | 产品名 |
| `vend_id` | style 编号(同款 + 多变体 共享)|
| `master_style` | 更高一级聚合(同 group / season)|
| `group` | 品类组 |
| `season` | 季节 |
| `gender` | 性别 |
| `class` | 品类 |
| `size` | 尺码 |
| `prices` | 单价 |
| `cost` | 成本(用于退货分析)|

**新平台**:已经上传到 Databricks,作为 `dim_product` 的源,需要 SCD2 管理(产品属性会变更)。

### 7.2 Basket_orders — 客户级订单视图

```sql
shopify_orders_order ⋈ line_items ⋈ customer
→ name / product_id / title / quantity / date / prices / customer_id / sku
```

服务于 PBI 的 `Cross-Sell` page(同一客户多次购买的 product 配对分析)。

**新平台**:`dwd.fact_orders` 的标准 join 视图,直接复用。

### 7.3 ProductA_B_Pairs — DAX 计算(不在 Panoply)

```dax
ProductA_B_Pairs = 
CROSSJOIN(
    DISTINCT(SELECTCOLUMNS(mysql_ers, "ClassA", mysql_ers[class])),
    DISTINCT(SELECTCOLUMNS(mysql_ers, "ClassB", mysql_ers[class]))
)
```

PBI 里 DAX 算的 class × class 交叉表,用于 cross-sell 矩阵分析。**新平台移到 SQL 层做更合理**(物化 `dim_class_pair`)。


---

## 8. 已盘点 vs 待补充 ⏳

### 8.1 已盘点(95%)

- ✅ 销售归因 — 行级 pipeline(Style_selling_dfNEW 全链路)
- ✅ 销售归因 — 订单级 pipeline(`_for_dollars2` + `_support` 系列)
- ✅ 退货 pipeline(双路径)
- ✅ 替换 pipeline(双路径)
- ✅ 运费 pipeline
- ✅ 订单篮子行为
- ✅ 产品主数据 + Basket_orders
- ✅ PBI 内 DAX 辅助构造(date dim / params / table refs)⭐ NEW

### Page_view 组成确认 + 新平台 1:1 映射（2026-06-16 NEW）

旧 `Page_view`（PBI 导入源）= 三源 LEFT JOIN，grain = day × GA_URL（产品页）：
- **`Shopify_sales_data`（销售侧）** = `shopify_orders_order` ⋈ `order_line_items` ⋈ `customer_type_info`，**anti-join `refund4` 按 (name, sku) 整行剔退**，过滤 `pre_tax_price≠0` + `total_order_qty<=30`；ET 日 `processed_at−5h`；ERS `sku` 主 / `item_description` 兜底取 category/gender/style#/season/desc；`GA_URL=CONCAT('/products/', handle)`。
- **`ga4_landing_page2`** = `ga4_landing_page` 按 (date, `/products`-归一 page path) 聚合 `itemviewevents`/`addtocarts`。
- **`ga4_sessions2`** = `ga4_sessions` 按 (date, `/products`-归一 landingpage, channelgroup) 聚合 sessions（PBI 里透视成 15 渠道列）。
- 销售数字（Unique Orders/Units Sold/Net Sales）**全来自 Shopify 侧**；GA4 侧只供 Event Count / Add to Cart / sessions（**GA4 不供 purchases/revenue/bounce**）。
- `customer_type_info` 在 Page_view 里**不影响结果**（没 select customer_type、LEFT JOIN 不改行数）。

**新平台 1:1 映射（Decision 54，不走 fact）**：
- `ga4_sessions2` → **`ga4_silver_traffic`**（GA4 Data API：date × landingPagePlusQueryString[剥 query 串] × sessionDefaultChannelGroup → sessions）
- `ga4_landing_page2` → **`ga4_silver_page`**（date × pagePath → itemViewEvents=event_count / addToCarts）
- `Shopify_sales_data` → 从 **dpsync 原始表**（order / order_line / refund + ERS + product.handle）按上述旧口径重建
- 退款口径：旧 = (order,sku) **整行剔**（部分退款也整行踢），与 fact 的按量净扣不同 → 报表用旧口径。

### 8.2 PBI 内的 DAX 辅助构造(已澄清)

这些**不是 Panoply 表**,而是 Sia 在 PBI 里用 DAX 构造的辅助对象。新平台用更合理的方式替代:

| PBI 对象 | DAX 定义 | 真相 | 新平台对应方案 |
|---|---|---|---|
| `filter_product` | `= mysql_ers` | 维度表别名引用 | 直接用 `dim_product` |
| `QuantityParam` | `= GENERATESERIES(0, 1000, 1)` | 数字滑块参数(0–1000 步长 1)| 前端 Next.js input slider 实现 |
| `Threshold` | `= GENERATESERIES(0, 10, 0.1)` | 小数滑块参数(0–10 步长 0.1)| 前端 Next.js input slider 实现 |
| `Table` | `= calendar(min, max of Style_selling_df.day)` | 行级 fact 的日历维度 | 统一到 `dim_date`(conformed dim)⭐ |
| `Table 2` | `= 'Table'` | `Table` 的引用复制 | 不需要 |
| `Table_extra` | `= calendar(min, max of CombinedTable.day)` | 订单级 fact 的日历维度 | 统一到 `dim_date`(conformed dim)|
| `Table_extra2` | `= 'Table_extra'` | 引用复制 | 不需要 |

⭐ **关键洞察**:PBI 里维护了**两个独立的 calendar 维度**(对应两个 fact 的日期范围),是因为 PBI/DAX 不易共享 conformed dim。新平台的 Kimball 模型用**单一 `dim_date`** 服务所有 fact,这是标准范式。

### 8.3 剩余待补充(5%,不阻塞)

- ⏳ PBI 其他 page 的底层数据来源(大部分应该复用 `Style_selling_df` + `Basket_orders`,少数可能有独立 query model)
- ⏳ `QuantityParam` / `Threshold` 在哪个具体 visual 上被使用(等做 Section 5 PBI 映射时同步揭晓)
- ⏳ `Measure 111 ~ 666` 的 DAX 公式(纯度量,不是数据,不影响数仓建模)

**这些剩余项可以在 Section 5(PBI Dashboard 映射)边做边补**。
---

**End of document.**
