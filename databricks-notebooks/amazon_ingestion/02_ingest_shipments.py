# Databricks notebook source
# MAGIC %md
# MAGIC # Amazon Shipments — Bronze + Silver (Weekly)
# MAGIC Source: SP-API /fba/inbound/v0/shipments. Grain: shipment.
# MAGIC
# MAGIC v2 (2026-05-29): shipments are fetched by the explicit ShipmentIdList present
# MAGIC in the items feed (QueryType=SHIPMENT), NOT by a LastUpdated date window.
# MAGIC Why: items keep getting updated as receiving trickles in, so the items feed
# MAGIC references shipments whose own status changed weeks ago; a date-windowed
# MAGIC shipments pull missed them and the gold inner join silently dropped received
# MAGIC units. Driving the shipments pull from item keys guarantees referential
# MAGIC completeness (Panoply parity — its connector was a full sync).
# MAGIC
# MAGIC Trigger: Workflows, Mon 06:00 ET — now runs AFTER notebook 01 (depends on items).

# COMMAND ----------
import requests, json, uuid, time
from datetime import datetime, timezone
from pyspark.sql import functions as F, types as T
from pyspark.sql.window import Window

SP_API_BASE = "https://sellingpartnerapi-na.amazon.com"
MARKETPLACE_ID = "ATVPDKIKX0DER"
CATALOG, SCHEMA = "mvdevdatabricks", "analytics_platform_32degrees"
SILVER_ITEM = f"{CATALOG}.{SCHEMA}.amazon_silver_shipment_item"   # NEW: read item keys
BRONZE = f"{CATALOG}.{SCHEMA}.amazon_bronze_shipments"
SILVER = f"{CATALOG}.{SCHEMA}.amazon_silver_shipment"

CLIENT_ID = dbutils.secrets.get(scope="amazon", key="lwa_client_id")
CLIENT_SECRET = dbutils.secrets.get(scope="amazon", key="lwa_client_secret")
REFRESH_TOKEN = dbutils.secrets.get(scope="amazon", key="lwa_refresh_token")

RUN_ID = str(uuid.uuid4())
RUN_TS = datetime.now(timezone.utc)
print(f"[INFO] run_id={RUN_ID}")

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

# Comprehensive status list (proven to work on this endpoint; covers every FBA
# inbound status so the ID-based query never filters a referenced shipment out).
STATUS_ALL = ("WORKING,READY_TO_SHIP,SHIPPED,RECEIVING,CANCELLED,DELETED,"
              "CLOSED,ERROR,IN_TRANSIT,DELIVERED,CHECKED_IN")

def fetch_shipments_by_ids(token, shipment_ids, chunk_size=50):
    """
    Fetch shipments by explicit ShipmentIdList (QueryType=SHIPMENT), chunked.
    Guarantees every shipment referenced by the items feed is retrieved, so the
    downstream gold inner join never drops received units.
    """
    url = f"{SP_API_BASE}/fba/inbound/v0/shipments"
    headers = {"x-amz-access-token": token, "Content-Type": "application/json"}
    ids = sorted({sid for sid in shipment_ids if sid})
    print(f"[INFO] fetching {len(ids)} distinct shipments by ID")
    for c in range(0, len(ids), chunk_size):
        chunk = ids[c:c + chunk_size]
        params = {"MarketplaceId": MARKETPLACE_ID, "QueryType": "SHIPMENT",
                  "ShipmentIdList": ",".join(chunk), "ShipmentStatusList": STATUS_ALL}
        page = 0
        while True:
            body = fetch_with_retry(url, headers, params)
            payload = body.get("payload", {})
            ships = payload.get("ShipmentData", []) or []
            print(f"[INFO] chunk={c // chunk_size} page={page} shipments={len(ships)}")
            for s in ships:
                yield page, s
            nxt = payload.get("NextToken")
            if not nxt:
                break
            params = {"NextToken": nxt, "MarketplaceId": MARKETPLACE_ID, "QueryType": "NEXT_TOKEN"}
            page += 1

# Distinct shipment_ids referenced by the items feed = the universe gold needs.
item_ship_ids = [r["shipment_id"] for r in
    spark.table(SILVER_ITEM).select("shipment_id").distinct().collect()]
print(f"[INFO] {len(item_ship_ids)} distinct shipment_ids in items feed")

access_token = get_access_token()
records = list(fetch_shipments_by_ids(access_token, item_ship_ids))
print(f"[INFO] total shipments fetched: {len(records)}")

# COMMAND ----------
# Bronze append — schema unchanged (window fields now hold the run date, since
# the pull is key-driven, not window-driven).
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
        RUN_TS.date(), RUN_TS, RUN_TS.date(), RUN_TS.date(),
        int(page), json.dumps(s), RUN_ID,
    ) for page, s in records]
    spark.createDataFrame(bronze_rows, schema=BRONZE_SCHEMA) \
        .write.format("delta").mode("append").saveAsTable(BRONZE)
    print(f"[OK] Bronze appended: {len(bronze_rows)} rows")
else:
    print("[INFO] No shipments fetched — Bronze unchanged")

# COMMAND ----------
# Silver typed + idempotent MERGE (unchanged from v1).
SILVER_SCHEMA = T.StructType([
    T.StructField("shipment_id",          T.StringType(),    False),
    T.StructField("shipment_name",        T.StringType(),    True),
    T.StructField("shipment_status",      T.StringType(),    True),
    T.StructField("destination_fc_id",    T.StringType(),    True),
    T.StructField("label_prep_type",      T.StringType(),    True),
    T.StructField("box_contents_source",  T.StringType(),    True),
    T.StructField("ship_from_name",       T.StringType(),    True),
    T.StructField("ship_from_city",       T.StringType(),    True),
    T.StructField("ship_from_state",      T.StringType(),    True),
    T.StructField("ship_from_country",    T.StringType(),    True),
    T.StructField("ship_from_postal_code",T.StringType(),    True),
    T.StructField("_bronze_run_id",       T.StringType(),    False),
    T.StructField("_silver_ingested_at",  T.TimestampType(), False),
])
if records:
    def addr(s, k):
        a = s.get("ShipFromAddress") or {}
        return a.get(k)
    silver_rows = [(
        s.get("ShipmentId"),
        s.get("ShipmentName"),
        s.get("ShipmentStatus"),
        s.get("DestinationFulfillmentCenterId"),
        s.get("LabelPrepType"),
        s.get("BoxContentsSource"),
        addr(s, "Name"),
        addr(s, "City"),
        addr(s, "StateOrProvinceCode"),
        addr(s, "CountryCode"),
        addr(s, "PostalCode"),
        RUN_ID, RUN_TS,
    ) for _, s in records]

    silver_df = spark.createDataFrame(silver_rows, schema=SILVER_SCHEMA)

    bad = silver_df.filter(F.col("shipment_id").isNull()).count()
    if bad > 0:
        raise AssertionError(f"[FAIL] {bad} rows with NULL shipment_id")
    print(f"[PASS] DQ — {silver_df.count()} rows have grain key")

    silver_dedup = (silver_df
        .withColumn("_rn", F.row_number().over(
            Window.partitionBy("shipment_id").orderBy(F.col("_silver_ingested_at").desc())))
        .filter(F.col("_rn") == 1).drop("_rn"))

    silver_dedup.createOrReplaceTempView("_stg_shipments")
    spark.sql(f"""
        MERGE INTO {SILVER} t
        USING _stg_shipments s
        ON t.shipment_id = s.shipment_id
        WHEN MATCHED THEN UPDATE SET *
        WHEN NOT MATCHED THEN INSERT *
    """)
    print("[OK] Silver MERGE complete")
else:
    print("[INFO] No shipments — Silver unchanged")

# COMMAND ----------
# Referential-completeness check — every item's shipment should now be in silver.
orphans = spark.sql(f"""
    SELECT COUNT(*) AS items_without_shipment
    FROM {SILVER_ITEM} i
    LEFT ANTI JOIN {SILVER} s ON i.shipment_id = s.shipment_id
""").collect()[0]["items_without_shipment"]
print(f"[CHECK] item rows still without a shipment after this run: {orphans}")

display(spark.sql(f"SELECT COUNT(*) AS silver_rows FROM {SILVER}"))
print(f"\n[OK] Run {RUN_ID} — {len(records)} shipments processed into {SILVER}")