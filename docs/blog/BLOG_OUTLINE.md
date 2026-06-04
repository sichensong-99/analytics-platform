# 技术博客大纲 — Flagship Post

## 推荐策略:一篇旗舰深度文 +（可选）两篇衍生

NORTH_STAR 第二原则:**深度 > 广度**。所以不写「我搭了个数据平台」这种泛文,而是用**最难被造假、最能体现工程判断**的那个故事当旗舰:**对账证伪（reconciliation as falsification）**。一篇讲透,面试官点进来能看 10 分钟、追问 3 层都接得住。

---

## 🚩 旗舰文

**Working title (EN):**
> *Trust, but verify: migrating an ecommerce sales metric to a Lakehouse — and why I refused to just match the legacy numbers*

**中文备选标题:**
> 《迁移指标时,我为什么拒绝「和旧系统对齐」——一个把残差打到 −1.5% 的对账故事》

**一句话钩子（开头必须立起来的论点）:**
> 迁移一个指标,最朴素的成功标准是「新数 == 旧数」。但如果旧系统本身有 bug,对齐它 = 继承它的 bug。真正的工程问题是:当唯一的参照物本身不可信时,你怎么知道你的新数是对的?

### 0. 背景（1 段,别长）
- 谁:保暖服装 DTC 品牌的电商团队;在替换 Power BI Service + 一个 legacy 仓（Panoply）。
- 指标:units by style × channel × week（件数,按款式 × 渠道 × 周）。
- 栈一句话带过:Shopify / Triple Whale → Databricks Lakehouse（Kimball）→ FastAPI metrics service → Next.js。详细架构甩链接到 README,这里不展开。
- 📊 规模数字:~10M order lines、25M+ TW attribution events。

### 1. 朴素陷阱:「把旧数对上不就行了?」
- 讲清为什么「对齐 legacy」是个错误的成功标准。
- legacy 是个黑盒,而且跑在另一套 SQL 方言上（埋钩子,第 3 节回收）。

### 2. 第一次尝试,被自己的对账证伪 ⭐（诚实本身就是亮点）
- 我的第一版口径:**整单排除 refund 订单**。
- 结果:残差不降反升,**1.97% → 6.57%**。
- 关键 takeaway:把对账当**证伪工具**,而不是「调到绿为止」的橡皮图章。自己的假设错了就推翻——这一段最能体现 senior 级的 epistemics。
- 📊 放这两个残差数字。

### 3. 读 legacy 源码来「定义真值」
- 跨方言取证:从源码特征认出 legacy 跑在 **BigQuery** 后端 → 对账 SQL 改用 `EXTRACT(ISOYEAR FROM day)`。
- 发现 legacy 的口径散在 **4 条 WHERE 过滤** + 基于 tag/label 的启发式（因为它没有结构化退款表）。
- takeaway:**Validate before acting**——读源码定口径,不靠猜。
- 💻 放一小段对比:legacy 的 tag 启发式 vs 后来用的 native 退款表(2~3 行就够,别贴大段)。

### 4. 重建:从「整单启发式」到「行级净扣」
- 新平台能用 Shopify 原生 `order_line_refund` / `return` 表 → 架构性简化（heuristic → authoritative source,这是 resume-grade 洞察）。
- `refunded_quantity = SUM(order_line_refund.quantity)`,覆盖全 restock_type（含 cancel）;净件数 = `quantity − refunded_quantity`。
- `is_sales_attributable` 布尔:把「这行算不算渠道可归因销量」的规则**在数据层物化一次**,替掉散落的 4 条 WHERE。
- 💻 放 `is_sales_attributable` 的定义片段 + 一句「为什么物化在 fact 层而不是查询层」。

### 5. 顺带量化出 legacy 的三个 bug（payoff 段,简历金句的来源）
- ① tag-based 退款识别只覆盖了 **22%** 的真实退款。
- ② 取消单被当成销量计入（cancel-as-sale）。
- ③ DST 时区:legacy 静态 `processed_at − 5h`,夏令时跨午夜订单系统性算错（~1% 漂移）→ 用 `from_utc_timestamp('America/New_York')` 修。
- 框成:**迁移中刻意保留的 3 个 correction**,不是「碰巧不一样」。
- takeaway:迁移 ≠ 复制;迁移是「带着判断把对的留下、把错的修掉」。

### 6. 重新定义 Trust Gate（方法论亮点）
- 不用「95% 的 bucket 通过」——低量款式的小分母会放大百分比、误导。
- 改成:**整体 < 2% AND 残差 100% 逐项归因**。
- 最终:**−1.51%**,残差 = EXC 2209 + refund 6573 + cancel 803（没有一句「剩下是噪声」）。
- 📊 放残差拆解这组数 + 最好配一张小柱状图（残差按因素分解）。

### 7. 让它长久可信:DQ-as-Gate
- 同一份**版本化 YAML 检查规格**,本地单测用、Spark 里对 ~10M 行 fact 也用（数据量大不能 `.toPandas()`）。
- fail-closed:硬失败就 fail gate、跳过所有下游,坏数永不落下游。
- 首跑就抓到一个真 bug:NULL `product_key`（某订单行的 SKU 不在产品主数据里）→ 按 Kimball 加 Unknown member（代理键 0）+ coalesce,而不是放任 NULL 外键。
- 💻 可放一条 YAML check 规格示例。

### 8. 收尾 takeaways（3 条,呼应开头）
- 迁移 ≠ 复制。
- 把对账当**证伪**,不当对齐。
- 读源码定真值,别猜。

### 📌 写作提示
- 长度:英文 2000~2800 字 / 中文 3000~4000 字。
- 代码片段:每段最多 3~6 行,够说明意图即可（别贴整 notebook）。
- 配图:架构图 1 张（或直接链 README）、残差拆解柱状图 1 张。
- 发哪:GitHub 仓 `docs/blog/` 留一份 + 个人博客 / 掘金 / Medium;README 顶部挂链接。
- 语言:外企 / 海外岗用 EN;国内中大厂可中文或双语。

---

## （可选）衍生文 2 篇 — 先别写,旗舰发完看反馈再决定
- **衍生 A:无人值守容器连 Lakehouse** —— OAuth 三模式（PAT / U2M / M2M）、为什么 headless 容器必须用 M2M、account-secret 要先 assign 到 workspace 这个坑、连接失败 reset 顺带当 token 刷新。（等 6.5 切通,素材最新鲜。）
- **衍生 B:用垂直切片交付一个数据平台** —— vertical-slice vs 瀑布、design-before-code、mock/databricks 双模式如何在权限中断时救场。
