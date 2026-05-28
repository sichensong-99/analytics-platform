# Databricks notebook source
# Databricks notebook source
# MAGIC %md
# MAGIC # Amazon Shipment Items — Bronze + Silver (Weekly)
# MAGIC Source: SP-API /fba/inbound/v0/shipmentItems
# MAGIC Grain: shipment x SKU. Trigger: Workflows, Mon 06:00 ET.
# MAGIC Schema: mvdevdatabricks.analytics_platform_32degrees (amazon_ prefix).

# COMMAND ----------
import requests, json, uuid, time
from datetime import datetime, timezone, timedelta
from pyspark.sql import functions as F, types as T

SP_API_BASE = "https://sellingpartnerapi-na.amazon.com"
MARKETPLACE_ID = "ATVPDKIKX0DER"
CATALOG, SCHEMA = "mvdevdatabricks", "analytics_platform_32degrees"
BRONZE = f"{CATALOG}.{SCHEMA}.amazon_bronze_shipment_items"
SILVER = f"{CATALOG}.{SCHEMA}.amazon_silver_shipment_item"
WINDOW_DAYS = 8   # 7-day need + 1-day overlap for idempotent replay

CLIENT_ID = dbutils.secrets.get(scope="amazon", key="lwa_client_id")
CLIENT_SECRET = dbutils.secrets.get(scope="amazon", key="lwa_client_secret")
REFRESH_TOKEN = dbutils.secrets.get(scope="amazon", key="lwa_refresh_token")

RUN_ID = str(uuid.uuid4())
RUN_TS = datetime.now(timezone.utc)
WINDOW_END = RUN_TS.date()
WINDOW_START = WINDOW_END - timedelta(days=WINDOW_DAYS)
print(f"[INFO] run_id={RUN_ID} window={WINDOW_START}..{WINDOW_END}")

# COMMAND ----------
def get_access_token():
    r = requests.post("https://api.amazon.com/auth/o2/token",
        data={"grant_type": "refresh_token", "client_id": CLIENT_ID,
              "client_secret": CLIENT_SECRET, "refresh_token": REFRESH_TOKEN},
        headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=30)
    r.raise_for_status()
    return r.json()["access_token"]

def fetch_with_retry(url, headers, params, max_attempts=5):
    backoff = 2.0
    for attempt in range(1, max_attempts + 1):
        resp = requests.get(url, headers=headers, params=params, timeout=60)
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code in (429, 500, 502, 503, 504):
            print(f"[WARN] attempt {attempt} status={resp.status_code}; sleep {backoff}s")
            time.sleep(backoff); backoff *= 2; continue
        print(f"[FAIL] status={resp.status_code} body={resp.text[:500]}")
        resp.raise_for_status()
    raise RuntimeError(f"Exhausted {max_attempts} attempts on {url}")

def fetch_all_items(token, start_date, end_date):
    url = f"{SP_API_BASE}/fba/inbound/v0/shipmentItems"
    headers = {"x-amz-access-token": token, "Content-Type": "application/json"}
    params = {"MarketplaceId": MARKETPLACE_ID, "QueryType": "DATE_RANGE",
              "LastUpdatedAfter": start_date.isoformat(),
              "LastUpdatedBefore": end_date.isoformat(),
              "ShipmentStatusList": "WORKING,READY_TO_SHIP,SHIPPED,RECEIVING,CANCELLED,DELETED,CLOSED,ERROR,IN_TRANSIT,DELIVERED,CHECKED_IN"}
    page = 0
    while True:
        body = fetch_with_retry(url, headers, params)
        payload = body.get("payload", {})
        items = payload.get("ItemData", []) or []
        print(f"[INFO] page={page} items={len(items)}")
        for it in items:
            yield page, it
        nxt = payload.get("NextToken")
        if not nxt:
            break
        params = {"NextToken": nxt, "MarketplaceId": MARKETPLACE_ID, "QueryType": "NEXT_TOKEN"}
        page += 1

access_token = get_access_token()
records = list(fetch_all_items(access_token, WINDOW_START, WINDOW_END))
print(f"[INFO] total items fetched: {len(records)}")

# COMMAND ----------
# Bronze append — EXPLICIT schema (do not let Spark infer types)
BRONZE_SCHEMA = T.StructType([
    T.StructField("ingestion_date",   T.DateType(),      False),
    T.StructField("ingestion_ts",     T.TimestampType(), False),
    T.StructField("api_window_start", T.DateType(),      False),
    T.StructField("api_window_end",   T.DateType(),      False),
    T.StructField("page_index",       T.IntegerType(),   False),
    T.StructField("raw_payload",      T.StringType(),    False),
    T.StructField("run_id",           T.StringType(),    False),
])

if records:
    bronze_rows = [(
        RUN_TS.date(), RUN_TS, WINDOW_START, WINDOW_END,
        int(page), json.dumps(item), RUN_ID,
    ) for page, item in records]
    bronze_df = spark.createDataFrame(bronze_rows, schema=BRONZE_SCHEMA)
    bronze_df.write.format("delta").mode("append").saveAsTable(BRONZE)
    print(f"[OK] Bronze appended: {len(bronze_rows)} rows")
else:
    print("[INFO] No items in window — Bronze unchanged")

# COMMAND ----------
# Silver typed + idempotent MERGE — EXPLICIT schema
SILVER_SCHEMA = T.StructType([
    T.StructField("shipment_id",             T.StringType(),    False),
    T.StructField("seller_sku",              T.StringType(),    False),
    T.StructField("fulfillment_network_sku", T.StringType(),    True),
    T.StructField("quantity_shipped",        T.IntegerType(),   True),
    T.StructField("quantity_received",       T.IntegerType(),   True),
    T.StructField("quantity_in_case",        T.IntegerType(),   True),
    T.StructField("prep_details",            T.StringType(),    True),
    T.StructField("_bronze_run_id",          T.StringType(),    False),
    T.StructField("_silver_ingested_at",     T.TimestampType(), False),
])

def _as_int(v):
    return int(v) if v is not None else None

if records:
    silver_rows = [(
        it.get("ShipmentId"),
        it.get("SellerSKU"),
        it.get("FulfillmentNetworkSKU"),
        _as_int(it.get("QuantityShipped")),
        _as_int(it.get("QuantityReceived")),
        _as_int(it.get("QuantityInCase")),
        json.dumps(it.get("PrepDetailsList")) if it.get("PrepDetailsList") else None,
        RUN_ID,
        RUN_TS,
    ) for _, it in records]

    silver_df = spark.createDataFrame(silver_rows, schema=SILVER_SCHEMA)

    # DQ gate: grain keys not null
    bad = silver_df.filter(F.col("shipment_id").isNull() | F.col("seller_sku").isNull()).count()
    if bad > 0:
        raise AssertionError(f"[FAIL] {bad} rows with NULL grain key")
    print(f"[PASS] DQ — {silver_df.count()} rows have grain keys")

    # A line can repeat across pages within one run; dedup to one row per grain
    # so MERGE doesn't hit "multiple source rows matched" error.
    silver_dedup = (silver_df
        .withColumn("_rn", F.row_number().over(
            __import__("pyspark.sql.window", fromlist=["Window"]).Window
            .partitionBy("shipment_id", "seller_sku")
            .orderBy(F.col("_silver_ingested_at").desc())))
        .filter(F.col("_rn") == 1).drop("_rn"))

    silver_dedup.createOrReplaceTempView("_stg_items")
    spark.sql(f"""
        MERGE INTO {SILVER} t
        USING _stg_items s
        ON t.shipment_id = s.shipment_id AND t.seller_sku = s.seller_sku
        WHEN MATCHED THEN UPDATE SET *
        WHEN NOT MATCHED THEN INSERT *
    """)
    print("[OK] Silver MERGE complete")
else:
    print("[INFO] No items — Silver unchanged")

# COMMAND ----------
display(spark.sql(f"SELECT COUNT(*) AS silver_rows FROM {SILVER}"))
display(spark.sql(f"SELECT * FROM {SILVER} ORDER BY _silver_ingested_at DESC LIMIT 20"))
print(f"\n[OK] Run {RUN_ID} — {len(records)} items processed into {SILVER}")

# COMMAND ----------

# Bronze retention — drop partitions older than 90 days
from datetime import datetime, timezone, timedelta
CATALOG, SCHEMA = "mvdevdatabricks", "analytics_platform_32degrees"
BRONZE = f"{CATALOG}.{SCHEMA}.amazon_bronze_shipment_items"
cutoff = (datetime.now(timezone.utc).date() - timedelta(days=90)).isoformat()
spark.sql(f"DELETE FROM {BRONZE} WHERE ingestion_date < DATE'{cutoff}'")
print(f"[OK] Bronze retention applied: dropped partitions before {cutoff}")