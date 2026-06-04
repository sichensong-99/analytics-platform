# Databricks notebook source
# MAGIC %md
# MAGIC # Phase 4.5 — Step 4: windowed ROAS + anomaly → gold_realtime_channel_health
# MAGIC
# MAGIC Aggregates the attributed stream into 5-min sliding windows per channel,
# MAGIC computes ROAS, and flags anomalies relative to each channel's own recent
# MAGIC healthy average.
# MAGIC
# MAGIC Writes via `foreachBatch + Delta MERGE`: each micro-batch applies the rule,
# MAGIC then upserts so each `(channel, window_start)` is a single live-updating row.
# MAGIC
# MAGIC Supports two execution modes through `RUN_MODE`:
# MAGIC
# MAGIC - `stream`: continuous near-real-time processing, every 30 seconds
# MAGIC - `backfill`: process all currently available data and stop
# MAGIC
# MAGIC **Prereqs:** notebooks 00 generator + 02 ingest + 03 join.

# COMMAND ----------

dbutils.widgets.dropdown("RUN_MODE", "stream", ["stream", "backfill"])
RUN_MODE = dbutils.widgets.get("RUN_MODE")

print(f"RUN_MODE = {RUN_MODE}")

def add_trigger(writer):
    if RUN_MODE == "backfill":
        return writer.trigger(availableNow=True)
    return writer.trigger(processingTime="30 seconds")

CATALOG = "mvdevdatabricks"
SCHEMA  = "analytics_platform_32degrees"

# 建议和 02 / 03 统一 checkpoint root
chk = f"/Volumes/{CATALOG}/{SCHEMA}/streaming_landing/_checkpoints_p1"

GOLD = f"{CATALOG}.{SCHEMA}.gold_realtime_channel_health"

# anomaly tuning
MIN_SPEND             = 20.0
BASELINE_LOOKBACK_MIN = 60
MIN_BASELINE_WINDOWS  = 3
ANOMALY_FACTOR        = 0.5

from pyspark.sql import functions as F
from delta.tables import DeltaTable

# COMMAND ----------

spark.sql(f"""
CREATE TABLE IF NOT EXISTS {GOLD} (
    window_start       TIMESTAMP,
    window_end         TIMESTAMP,
    channel            STRING,
    total_spend        DOUBLE,
    attributed_revenue DOUBLE,
    roas               DOUBLE,
    order_count        BIGINT,
    is_anomaly         BOOLEAN,
    last_updated       TIMESTAMP
) USING DELTA
""")

windowed = (
    spark.readStream
        .option("skipChangeCommits", "true")
        .table(f"{CATALOG}.{SCHEMA}.silver_realtime_attributed")
        .withWatermark("event_time", "2 minutes")
        .groupBy(
            F.window("event_time", "5 minutes", "1 minute"),
            F.col("channel"),
        )
        .agg(
            F.round(F.sum("ad_spend"), 2).alias("total_spend"),
            F.round(F.sum("attributed_revenue"), 2).alias("attributed_revenue"),
            F.sum("is_attributed").alias("order_count"),
        )
        .select(
            F.col("window.start").alias("window_start"),
            F.col("window.end").alias("window_end"),
            "channel",
            "total_spend",
            "attributed_revenue",
            F.round(
                F.col("attributed_revenue")
                / F.when(F.col("total_spend") == 0, None).otherwise(F.col("total_spend")),
                2,
            ).alias("roas"),
            "order_count",
        )
)

# COMMAND ----------

def upsert_to_gold(batch_df, batch_id):
    if batch_df.isEmpty():
        return

    baseline = (
        spark.table(GOLD)
            .filter(~F.col("is_anomaly"))
            .filter(
                F.col("window_start") >=
                F.expr(f"current_timestamp() - INTERVAL {BASELINE_LOOKBACK_MIN} MINUTES")
            )
            .groupBy("channel")
            .agg(
                F.avg("roas").alias("baseline_roas"),
                F.count("*").alias("baseline_n")
            )
    )

    enriched = (
        batch_df.join(baseline, "channel", "left")
            .withColumn(
                "is_anomaly",
                (F.col("total_spend") >= F.lit(MIN_SPEND))
                & (F.col("baseline_n") >= F.lit(MIN_BASELINE_WINDOWS))
                & (F.col("roas") < F.col("baseline_roas") * F.lit(ANOMALY_FACTOR)),
            )
            .withColumn("is_anomaly", F.coalesce(F.col("is_anomaly"), F.lit(False)))
            .withColumn("last_updated", F.current_timestamp())
            .drop("baseline_roas", "baseline_n")
    )

    (
        DeltaTable.forName(spark, GOLD)
            .alias("t")
            .merge(
                enriched.alias("s"),
                """
                t.channel = s.channel
                AND t.window_start = s.window_start
                """
            )
            .whenMatchedUpdateAll()
            .whenNotMatchedInsertAll()
            .execute()
    )


gold_writer = (
    windowed.writeStream
        .outputMode("update")
        .foreachBatch(upsert_to_gold)
        .option("checkpointLocation", f"{chk}/gold_write")
)

q_gold = (
    add_trigger(gold_writer)
        .start()
)

print("gold stream status:")
print(q_gold.status)

if RUN_MODE == "backfill":
    q_gold.awaitTermination()
    print("Backfill completed for gold channel health stream.")

# COMMAND ----------

display(spark.sql(f"""
    SELECT channel,
           window_start,
           window_end,
           total_spend,
           attributed_revenue,
           roas,
           order_count,
           is_anomaly,
           last_updated
    FROM {GOLD}
    WHERE window_start >= current_timestamp() - INTERVAL 20 MINUTES
    ORDER BY window_start DESC, channel
"""))

display(spark.sql(f"""
    SELECT *
    FROM {GOLD}
    WHERE is_anomaly
    ORDER BY window_start DESC, channel
"""))

# Stop manually when needed:
# q_gold.stop()

# COMMAND ----------

# MAGIC %md
# MAGIC ### Verify (after ~5–7 min, so a crash window can close + get a baseline)

# COMMAND ----------

display(spark.sql(f"""
    SELECT channel, window_start, total_spend, attributed_revenue, roas,
           order_count, is_anomaly
    FROM {GOLD}
    WHERE window_start >= current_timestamp() - INTERVAL 20 MINUTES
    ORDER BY window_start DESC, channel
"""))

# COMMAND ----------

# anomalies only — facebook crash windows should show up here
display(spark.sql(f"SELECT * FROM {GOLD} WHERE is_anomaly ORDER BY window_start DESC"))

# COMMAND ----------

# MAGIC %md Stop with: `q_gold.stop()`