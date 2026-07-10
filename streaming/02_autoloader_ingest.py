# Databricks notebook source
# MAGIC %md
# MAGIC # Phase 4.5 — Step 2 (P1-hardened): Auto Loader ingest + dedup → silver
# MAGIC
# MAGIC Auto Loader ingest + watermark dedup → silver.
# MAGIC
# MAGIC This notebook supports two execution modes:
# MAGIC
# MAGIC - `RUN_MODE = stream`: continuous near-real-time ingestion
# MAGIC - `RUN_MODE = backfill`: process all currently available files and stop
# MAGIC
# MAGIC This demonstrates batch/stream unification through Structured Streaming triggers.

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
VOLUME  = "streaming_landing"

base       = f"/Volumes/{CATALOG}/{SCHEMA}/{VOLUME}"
orders_src = f"{base}/orders"
ads_src    = f"{base}/ads"
chk        = f"{base}/_checkpoints_p1"

from pyspark.sql import functions as F
from pyspark.sql.types import StructType, StructField, StringType, DoubleType

orders_schema = StructType([
    StructField("order_id",     StringType()),
    StructField("customer_id",  StringType()),
    StructField("order_amount", DoubleType()),
    StructField("event_time",   StringType()),
])

ads_schema = StructType([
    StructField("ad_event_id", StringType()),
    StructField("order_id",    StringType()),
    StructField("channel",     StringType()),
    StructField("ad_spend",    DoubleType()),
    StructField("event_time",  StringType()),
])

# COMMAND ----------

# MAGIC %md
# MAGIC ### Stream 1 — orders → silver_realtime_orders
# MAGIC Deduped on `order_id`.

# COMMAND ----------

orders_stream = (
    spark.readStream.format("cloudFiles")
        .option("cloudFiles.format", "json")
        .option("cloudFiles.schemaLocation", f"{chk}/orders_schema")
        .option("pathGlobFilter", "*.json")
        .schema(orders_schema)
        .load(orders_src)
        .withColumn("event_time", F.to_timestamp("event_time"))
        .withWatermark("event_time", "10 minutes")
        .dropDuplicatesWithinWatermark(["order_id"])
        .withColumn("ingestion_time", F.current_timestamp())
)

orders_writer = (
    orders_stream.writeStream
        .option("checkpointLocation", f"{chk}/orders_write")
)

q_orders = (
    add_trigger(orders_writer)
        .toTable(f"{CATALOG}.{SCHEMA}.silver_realtime_orders")
)

# COMMAND ----------

# MAGIC %md
# MAGIC ### Stream 2 — ads → silver_realtime_ads
# MAGIC Deduped on `ad_event_id`.

# COMMAND ----------

ads_stream = (
    spark.readStream.format("cloudFiles")
        .option("cloudFiles.format", "json")
        .option("cloudFiles.schemaLocation", f"{chk}/ads_schema")
        .option("pathGlobFilter", "*.json")
        .schema(ads_schema)
        .load(ads_src)
        .withColumn("event_time", F.to_timestamp("event_time"))
        .withWatermark("event_time", "10 minutes")
        .dropDuplicatesWithinWatermark(["ad_event_id"])
        .withColumn("ingestion_time", F.current_timestamp())
)

ads_writer = (
    ads_stream.writeStream
        .option("checkpointLocation", f"{chk}/ads_write")
)

q_ads = (
    add_trigger(ads_writer)
        .toTable(f"{CATALOG}.{SCHEMA}.silver_realtime_ads")
)

# COMMAND ----------

# MAGIC %md
# MAGIC ### Check streaming query status

# COMMAND ----------

print("orders stream status:")
print(q_orders.status)

print("ads stream status:")
print(q_ads.status)

# COMMAND ----------

# MAGIC %md
# MAGIC ### Optional: wait for completion in backfill mode
# MAGIC
# MAGIC In `backfill` mode, this makes the notebook wait until both availableNow
# MAGIC streams finish. In `stream` mode, do not wait here unless you want the
# MAGIC notebook/job to stay attached forever.

# COMMAND ----------

if RUN_MODE == "backfill":
    q_orders.awaitTermination()
    q_ads.awaitTermination()
    print("Backfill completed for both orders and ads streams.")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Optional: stop streams manually when needed
# MAGIC
# MAGIC Only run this cell when you want to stop the continuous streams.

# COMMAND ----------

# q_orders.stop()
# q_ads.stop()

# COMMAND ----------

# MAGIC %md ### Verify (after ~1–2 min)

# COMMAND ----------

display(spark.sql(f"""
    SELECT COUNT(*) AS rows, COUNT(DISTINCT order_id) AS distinct_orders
    FROM {CATALOG}.{SCHEMA}.silver_realtime_orders
"""))
# rows == distinct_orders  ->  dedup is working (no duplicate order_ids landed)

# COMMAND ----------

display(spark.sql(f"""
    SELECT channel,
           COUNT(*)               AS ad_events,
           ROUND(SUM(ad_spend),2) AS total_spend,
           SUM(CASE WHEN order_id IS NOT NULL THEN 1 ELSE 0 END) AS attributed
    FROM {CATALOG}.{SCHEMA}.silver_realtime_ads
    GROUP BY channel
    ORDER BY total_spend DESC
"""))

# COMMAND ----------

# MAGIC %md Stop with: `q_orders.stop(); q_ads.stop()`