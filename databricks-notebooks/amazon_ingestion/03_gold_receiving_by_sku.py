# Databricks notebook source
# MAGIC %md
# MAGIC # Amazon Gold — Receiving Summary by SKU
# MAGIC items (shipment x SKU) JOIN shipments (metadata) ON shipment_id.
# MAGIC Full rebuild each run (small data). Replicates legacy Panoply query-model join.
# MAGIC Trigger: Workflows, after notebook 01 + 02 both succeed.

# COMMAND ----------
from pyspark.sql import functions as F
from datetime import datetime, timezone

CATALOG, SCHEMA = "analytics_catalog", "analytics_platform"
SILVER_ITEM = f"{CATALOG}.{SCHEMA}.amazon_silver_shipment_item"
SILVER_SHIP = f"{CATALOG}.{SCHEMA}.amazon_silver_shipment"
GOLD = f"{CATALOG}.{SCHEMA}.amazon_gold_receiving_by_sku"

items = spark.table(SILVER_ITEM).alias("i")
ships = spark.table(SILVER_SHIP).alias("s")

gold = (
    items.join(ships, on="shipment_id", how="left")
    .select(
        F.col("shipment_id"),
        F.col("s.shipment_name"),
        F.col("s.shipment_status"),
        F.col("s.destination_fc_id"),
        F.col("i.seller_sku"),
        F.col("i.fulfillment_network_sku"),
        F.col("i.quantity_shipped"),
        F.col("i.quantity_received"),
        F.col("i.quantity_in_case"),
        (F.coalesce(F.col("i.quantity_shipped"), F.lit(0))
         - F.coalesce(F.col("i.quantity_received"), F.lit(0))).alias("receiving_gap"),
        F.lit(datetime.now(timezone.utc)).cast("timestamp").alias("_built_at"),
    )
)

# DQ: count items that didn't match a shipment (informational)
unmatched = items.join(ships, on="shipment_id", how="left_anti").count()
total_items = items.count()
print(f"[INFO] items={total_items} | items without shipment metadata={unmatched} "
      f"({unmatched/total_items:.2%})" if total_items else "[INFO] no items")

gold.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(GOLD)
print(f"[OK] Gold rebuilt: {gold.count()} rows into {GOLD}")

# COMMAND ----------
display(spark.sql(f"SELECT * FROM {GOLD} ORDER BY shipment_status, shipment_id LIMIT 30"))