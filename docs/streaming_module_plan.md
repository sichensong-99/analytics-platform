# Streaming Module Plan (Phase 4.5)

## 元信息
名称:Real-time Channel Anomaly Detection
位置:Phase 4 完成后启动
工作量:5-7 天
触发条件:Phase 4 完成,Databricks 数仓已稳定运行
文档归档位置:docs/streaming_module_plan.md
> Status: 📦 已锁定方案,Phase 4 完成后启动
> 工作量:5-7 天

---

## 业务

**实时渠道异常监控(Real-time Channel Anomaly Detection)**

当广告渠道 ROAS 出现异常时(比如低于过去 24 小时均值 50%),实时告警,让运营团队及时调整投放,避免预算浪费。

**业务故事**:
> "广告每分钟在烧钱,如果 Facebook 渠道凌晨突然 ROAS 暴跌(创意失效或恶意点击),需要在 10 分钟内发现并暂停广告,而不是等到第二天。"

---

## 技术架构
模拟订单 + 广告事件(JSON 文件)
↓
Auto Loader (streaming ingest)
↓
silver_realtime_orders + silver_realtime_ads
↓
Stream-Stream Join (via order_id + watermark)
↓
Sliding Window 5min Aggregation
↓
gold_realtime_channel_health
↓
Anomaly Rule (ROAS < avg_24h * 0.5 → alert)
↓
FastAPI /metrics/channel-health
↓
Next.js 实时大屏页面(每 10 秒刷新)
---

## 实现清单

### P0(3 天 - 基础版)
1. [ ] Python 模拟数据生成器
   - 每秒 1 条订单 + 1 条广告事件
   - 写入指定目录的 JSON 文件
   - 字段按 silver 表 schema 设计
2. [ ] Auto Loader streaming notebook
   - 监听文件目录
   - 写入 silver Delta 表
3. [ ] 5-min sliding window 聚合
4. [ ] channel-level metrics 计算
5. [ ] Simple anomaly rule(阈值告警)

### P1(再 2-3 天 - 生产级)⭐ 别漏
6. [ ] Stream-stream join
   - orders 流 + ads 流 via order_id
   - 用 watermark 控制 state size
7. [ ] Checkpoint + Exactly-once semantics
   - 配置 checkpoint 路径
   - 演示重启恢复
8. [ ] Watermark + 乱序数据处理
   - watermark = 10 分钟
   - 演示晚到事件如何被正确处理
9. [ ] dropDuplicatesWithinWatermark 去重
   - 防止重复订单进入聚合
10. [ ] 流批一体(Unified Streaming + Batch on Delta)
    - gold_realtime_channel_health 与 dws.channel_performance 共享存储
    - 通过 partition / view 区分

---

## 架构亮点

- **Delta Lake unified streaming + batch (流批一体)**

---

## 数据 Schema(预设计)

### `silver_realtime_orders`
order_id        STRING
customer_id     STRING
order_amount    DECIMAL(10,2)
event_time      TIMESTAMP
ingestion_time  TIMESTAMP
### `silver_realtime_ads`

ad_event_id     STRING
order_id        STRING (nullable, 关联用)
channel         STRING (facebook/google/tiktok/...)
ad_spend        DECIMAL(10,2)
event_time      TIMESTAMP
ingestion_time  TIMESTAMP
### `gold_realtime_channel_health`

window_start    TIMESTAMP
window_end      TIMESTAMP
channel         STRING
total_spend     DECIMAL
attributed_revenue DECIMAL
roas            DECIMAL
order_count     INT
is_anomaly      BOOLEAN
last_updated    TIMESTAMP

---

## 关键参数(预设)

| 参数 | 值 | 说明 |
|---|---|---|
| 滑动窗口大小 | 5 min | 业务上够及时 |
| 滑动间隔 | 1 min | 每分钟出新数据 |
| Watermark | 10 min | 容忍晚到 10 分钟 |
| Checkpoint 间隔 | 30 sec | 平衡恢复速度和性能 |
| Trigger 模式 | ProcessingTime("30 seconds") | 30 秒处理一批 |
| 异常阈值 | ROAS < avg_last_24h * 0.5 | 简单可解释 |

---

## 简历素材(完成后用)

基于 Databricks Structured Streaming + Auto Loader 实现端到端流式数据 pipeline:

实时摄入订单与广告事件,通过 stream-stream join 关联多流数据
Watermark + dropDuplicatesWithinWatermark 处理乱序与重复
Checkpoint 实现 exactly-once 语义与故障恢复
5 分钟滑动窗口聚合渠道级 ROAS,基于阈值规则触发异常告警
Delta Lake 流批一体存储,实时聚合与离线聚合表共享底层存储,
避免数据冗余与口径不一致

完整简历素材表述:

> Built a production-grade streaming pipeline using Databricks Structured 
> Streaming with exactly-once semantics, stream-stream joins, watermark-based 
> late-data handling, and unified streaming-batch storage on Delta Lake.

---

## 面试 Q&A 预演

| 面试问题 | 准备答法 |
|---|---|
| 为什么用 Auto Loader 不用 Kafka? | 业务规模 + 简化运维 + Databricks 原生集成 |
| 怎么保证 exactly-once? | Checkpoint + 幂等写入 + Delta ACID |
| 怎么处理乱序数据? | Watermark = 10 min,超过丢弃,业务可接受 |
| 流批一体怎么实现? | Delta Lake 统一存储,Spark 统一引擎 |
| 多流 join 的挑战? | State size 控制(watermark) + key skew |
| 为什么不用 ML 做异常检测? | 简单可解释,生产环境 ML 维护成本高 |

---

## 触发条件

✅ Phase 4 完成(批处理 pipeline 稳定运行)
✅ 不要在 Phase 4 之前做(概念会乱)
✅ 不要跳过 P1(简历差距巨大)