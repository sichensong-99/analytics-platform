# Leader Demo — Slice 1 (Style × Channel Quantity)

## 0. Setup (demo 前 30 分钟)
- 启动 metrics-service:`uv run uvicorn app.main:app --reload`
- 启动 frontend:`npm run dev`(frontend 目录)
- 打开 reconciliation 报告:docs/reconciliation/reports/{date}_summary.xlsx
- 浏览器 tab:① 网页 portal ② Excel 对账报告 ③ PBI Style_selling_df 页(对比用)

## 1. 开场(2 min)— 这是什么
- "今天给您看我做的内部分析平台 Slice 1,正好对应 PBI 的 Style-channel 页"
- "Slice 1 是端到端打通:Shopify + TW → Databricks 数仓 → API 服务 → 网页"
- "为什么叫 Slice 1 —— 用 vertical slice 方法论,一个完整 PBI 页一个 slice,
   边交付边收反馈,不等所有 page 都做完才给您看"

## 2. 看网页(3 min)— Leader 关心的"能用"
- 打开 portal,登录(JWT)
- 进 Style-channel quantity 页,选 week 28(2025-07-07 ~ 13)
- 演示:① 切换 channel ② 切换 season ③ 切换 style ④ CSV 导出

## 3. 对账(5 min)— 信任建立环节 ⭐
- 打开 Excel 报告
- "Leader 您最关心的肯定是数对不对 —— 我对了 Style_selling_df week 28
   一整周,180,670 vs 183,438,差 1.51%,在我们设的 2% trust gate 内"
- "差的 2,880 件不是错,我能逐项告诉您是什么:
   * EXC 单 2,209 件 ✓
   * 原生 refund 6,573 件 ✓(旧报表 tag 反推只抓到 22% 的退货单)
   * cancel 单 803 件 ✓(旧报表不算 cancel,新平台净扣)
   * 还差的几百件是 replacement,Fivetran 同事正在同步"
- "这些差异不是 bug,是新平台主动修正旧报表的精度缺陷"

## 4. 看底层(5 min)— 简历级技术深度
- 切到 Databricks
- "底下其实是个 Kimball 维度模型 —— 一个 fact + 三个 dim"
- 跑一个 SQL:`SELECT iso_week, SUM(quantity - refunded_quantity) AS net_units
                FROM fact_orders_line WHERE is_sales_attributable = TRUE
                GROUP BY iso_week ORDER BY iso_week DESC LIMIT 4`
- "fact 表 996 万行,DST 时区、TW last-touch 去重、行级 refund netting
   都已经处理好,所有 PBI 数都从这一张算 —— 单一口径"

## 5. 路径(3 min)— 接下来做什么
- "Slice 1 是第一个 PBI 页。下一个准备做 page_view,等 TW Web Analytics
   接进 Databricks 就启动"
- "未来 Phase 4 接 Workflows 自动调度,Phase 4.5 加实时模块"
- "全部做完节省 $XX/月订阅费(Phase 6 算完整 ROI)"

## 6. 收尾(2 min)
- "您想看下一个哪个 PBI 页?"
- "您对当前这一页希望加什么?"
- "数据对不对您还想抽哪一周看看?"

---

## 应急 FAQ
- Q:为什么不直接连 Power BI 的数据?
  A:Power BI 后面是 Panoply,Panoply 公司今年要砍预算停掉,所以要换。
- Q:为什么 1.51% 不是 0%?
  A:见 §3,旧报表本身有 ~1.5% 的低估(漏退货 + 漏 cancel),
     新平台是把数据做精确了。
- Q:做完要多久?
  A:Slice 1 一周一个页节奏,共 N 个页;Phase 4 调度 + 4.5 实时 + 5 服务化 + 6 部署。
- Q:出了问题谁修?
  A:我维护,文档全部进 GitHub,有 onboarding 文档(后续补)。