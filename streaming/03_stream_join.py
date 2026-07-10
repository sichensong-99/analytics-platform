# Databricks notebook source
# MAGIC %md
# MAGIC # Phase 4.5 — Step 3: stream-stream join (ads ⟕ orders) → silver_realtime_attributed
# MAGIC
# MAGIC Joins the two silver streams on `order_id` so each ad event carries the
# MAGIC revenue of the order it drove.
# MAGIC
# MAGIC This version reads Delta streaming sources with `skipChangeCommits=true`
# MAGIC so the stream will not fail if the upstream silver tables were previously
# MAGIC deleted/overwritten during testing.
# MAGIC
# MAGIC Supports two execution modes:
# MAGIC
# MAGIC - `RUN_MODE = stream`: continuous near-real-time join
# MAGIC - `RUN_MODE = backfill`: process all currently available data and stop
# MAGIC
# MAGIC **Why LEFT join (not inner):** during a ROAS crash the ads have no
# MAGIC `order_id`, and we must still keep that spend. An inner join would silently
# MAGIC drop it and the anomaly would never fire.

# COMMAND ----------

# --- Job parameter / notebook parameter ---
dbutils.widgets.dropdown("RUN_MODE", "stream", ["stream", "backfill"])
RUN_MODE = dbutils.widgets.get("RUN_MODE")

print(f"RUN_MODE = {RUN_MODE}")

def add_trigger(writer):
    """
    One streaming writer, two execution modes.

    stream:
      Runs continuously every 30 seconds.

    backfill:
      Processes all currently available data and then stops.
    """
    if RUN_MODE == "backfill":
        return writer.trigger(availableNow=True)

    return writer.trigger(processingTime="30 seconds")

# COMMAND ----------

CATALOG = "analytics_catalog"
SCHEMA  = "analytics_platform"

chk = f"/Volumes/{CATALOG}/{SCHEMA}/streaming_landing/_checkpoints_p1"

from pyspark.sql import functions as F

# COMMAND ----------

# MAGIC %md
# MAGIC ### Watermarks
# MAGIC Watermark = "stop waiting for events older than this", letting Spark clean
# MAGIC up join state and emit unmatched null rows.
# MAGIC
# MAGIC We use 2 minutes for near-real-time synthetic testing.

# COMMAND ----------

orders = (
    spark.readStream
        .option("skipChangeCommits", "true")
        .table(f"{CATALOG}.{SCHEMA}.silver_realtime_orders")
        .selectExpr(
            "order_id AS o_order_id",
            "order_amount",
            "event_time AS order_time"
        )
        .withWatermark("order_time", "2 minutes")
)

ads = (
    spark.readStream
        .option("skipChangeCommits", "true")
        .table(f"{CATALOG}.{SCHEMA}.silver_realtime_ads")
        .selectExpr(
            "ad_event_id",
            "order_id AS a_order_id",
            "channel",
            "ad_spend",
            "event_time AS ad_time"
        )
        .withWatermark("ad_time", "2 minutes")
)

# COMMAND ----------

# MAGIC %md
# MAGIC ### LEFT stream-stream join
# MAGIC The time-range condition bounds the join state and is required for
# MAGIC outer stream-stream joins.

# COMMAND ----------

joined = (
    ads.join(
        orders,
        (F.col("a_order_id") == F.col("o_order_id"))
        & (F.col("ad_time") >= F.col("order_time") - F.expr("INTERVAL 2 MINUTES"))
        & (F.col("ad_time") <= F.col("order_time") + F.expr("INTERVAL 2 MINUTES")),
        how="left",
    )
    .select(
        "ad_event_id",
        "channel",
        "ad_spend",
        F.coalesce(F.col("order_amount"), F.lit(0.0)).alias("attributed_revenue"),
        F.when(F.col("o_order_id").isNotNull(), 1).otherwise(0).alias("is_attributed"),
        F.col("ad_time").alias("event_time"),
    )
    .withColumn("ingestion_time", F.current_timestamp())
)

# COMMAND ----------

join_writer = (
    joined.writeStream
        .option("checkpointLocation", f"{chk}/attributed_write")
)

q_join = (
    add_trigger(join_writer)
        .toTable(f"{CATALOG}.{SCHEMA}.silver_realtime_attributed")
)

# COMMAND ----------

print("join stream status:")
print(q_join.status)

# COMMAND ----------

# MAGIC %md
# MAGIC ### Optional: wait for completion in backfill mode
# MAGIC
# MAGIC In `backfill` mode, this makes the notebook wait until the availableNow
# MAGIC stream finishes. In `stream` mode, do not wait here unless you want the
# MAGIC notebook/job to stay attached forever.

# COMMAND ----------

if RUN_MODE == "backfill":
    q_join.awaitTermination()
    print("Backfill completed for attributed join stream.")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Verify
# MAGIC Matched attributed rows appear immediately; unmatched rows from the left join
# MAGIC may wait until the watermark passes, so crash spend can show up a few minutes late.

# COMMAND ----------

display(spark.sql(f"""
    SELECT channel,
           COUNT(*)                          AS ad_events,
           ROUND(SUM(ad_spend), 2)           AS spend,
           ROUND(SUM(attributed_revenue), 2) AS revenue,
           ROUND(SUM(attributed_revenue) / NULLIF(SUM(ad_spend), 0), 2) AS roas,
           SUM(is_attributed)                AS attributed
    FROM {CATALOG}.{SCHEMA}.silver_realtime_attributed
    GROUP BY channel
    ORDER BY spend DESC
"""))

# COMMAND ----------

# MAGIC %md
# MAGIC `facebook` should show **high spend, low revenue, low ROAS** if a crash
# MAGIC window happened — that's the signal Step 4 turns into a per-window anomaly
# MAGIC flag.
# MAGIC
# MAGIC Stop with: `q_join.stop()`

# COMMAND ----------

# q_join.stop()

# COMMAND ----------

# MAGIC %md
# MAGIC ### Verify (after ~3–5 min)
# MAGIC Matched (attributed) rows appear immediately; unmatched rows wait until the
# MAGIC watermark passes, so crash spend shows up a few minutes late.

# COMMAND ----------

display(spark.sql(f"""
    SELECT channel,
           COUNT(*)                          AS ad_events,
           ROUND(SUM(ad_spend), 2)           AS spend,
           ROUND(SUM(attributed_revenue), 2) AS revenue,
           ROUND(SUM(attributed_revenue) / NULLIF(SUM(ad_spend), 0), 2) AS roas,
           SUM(is_attributed)                AS attributed
    FROM {CATALOG}.{SCHEMA}.silver_realtime_attributed
    GROUP BY channel
    ORDER BY spend DESC
"""))

# COMMAND ----------

# MAGIC %md
# MAGIC `facebook` should show **high spend, low revenue, low ROAS** if a crash
# MAGIC window happened — that's the signal Step 4 turns into a per-window anomaly
# MAGIC flag.
# MAGIC
# MAGIC Stop with: `q_join.stop()`