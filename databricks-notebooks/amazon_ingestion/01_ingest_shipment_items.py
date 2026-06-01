# Databricks notebook source
# MAGIC %md
# MAGIC # Amazon Shipment Items — Bronze + Silver (Weekly)
# MAGIC Source:
# MAGIC   Stage 1 discovery: SP-API /fba/inbound/v0/shipmentItems
# MAGIC   Stage 2 full pull: SP-API /fba/inbound/v0/shipments/{shipmentId}/items
# MAGIC
# MAGIC Grain: shipment x SKU
# MAGIC Trigger: Workflows, Mon 06:00 ET
# MAGIC
# MAGIC v3 (2026-05-29): TWO-STAGE pull for completeness, with single-page shipment item pull.
# MAGIC
# MAGIC Stage 1 — Discover active ShipmentIds via DATE_RANGE window.
# MAGIC           The windowed item rows are NOT used as final item data because DATE_RANGE
# MAGIC           can silently omit SKU lines whose LastUpdated timestamp predates the window.
# MAGIC
# MAGIC Stage 2 — For each discovered ShipmentId, pull FULL item list via:
# MAGIC           GET /fba/inbound/v0/shipments/{shipmentId}/items
# MAGIC           No date filter. No NextToken pagination.
# MAGIC
# MAGIC Why:
# MAGIC   The original single-stage DATE_RANGE pull dropped older SKU lines of active shipments.
# MAGIC   Example: FBA19CRBL6RZ returned 12 of 20 via date-window logic, but
# MAGIC   /shipments/{shipmentId}/items returns 20 item rows / 20 distinct SKUs.
# MAGIC
# MAGIC Important:
# MAGIC   Do NOT paginate Stage 2 with NextToken. In testing, doing so caused repeated rows/pages
# MAGIC   and excessive requests, leading to 429 throttling.

# COMMAND ----------

import requests
import json
import uuid
import time
import random
from datetime import datetime, timezone, timedelta

from pyspark.sql import functions as F, types as T
from pyspark.sql.window import Window

# COMMAND ----------

SP_API_BASE = "https://sellingpartnerapi-na.amazon.com"
MARKETPLACE_ID = "ATVPDKIKX0DER"

CATALOG = "mvdevdatabricks"
SCHEMA = "analytics_platform_32degrees"

BRONZE = f"{CATALOG}.{SCHEMA}.amazon_bronze_shipment_items"
SILVER = f"{CATALOG}.{SCHEMA}.amazon_silver_shipment_item"

# Discovery window only.
# This finds shipments active/recently updated in the last N days.
# Do not use DATE_RANGE result rows as final item rows.
WINDOW_DAYS = 8

# Conservative throttle for per-shipment item pulls.
# Helps reduce 429s when there are many shipments.
PER_SHIPMENT_SLEEP_SECONDS = 0.8

CLIENT_ID = dbutils.secrets.get(scope="amazon", key="lwa_client_id")
CLIENT_SECRET = dbutils.secrets.get(scope="amazon", key="lwa_client_secret")
REFRESH_TOKEN = dbutils.secrets.get(scope="amazon", key="lwa_refresh_token")

RUN_ID = str(uuid.uuid4())
RUN_TS = datetime.now(timezone.utc)

WINDOW_END = RUN_TS.date()
WINDOW_START = WINDOW_END - timedelta(days=WINDOW_DAYS)

print(f"[INFO] run_id={RUN_ID} discovery_window={WINDOW_START}..{WINDOW_END}")

# COMMAND ----------

def get_access_token() -> str:
    r = requests.post(
        "https://api.amazon.com/auth/o2/token",
        data={
            "grant_type": "refresh_token",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "refresh_token": REFRESH_TOKEN,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def fetch_with_retry(url, headers, params=None, max_attempts=6):
    """
    Shared GET wrapper.

    Handles:
      - 429 throttling
      - transient 5xx errors
      - Retry-After header when Amazon provides it
      - exponential backoff with jitter
    """
    backoff = 2.0

    for attempt in range(1, max_attempts + 1):
        resp = requests.get(url, headers=headers, params=params, timeout=60)

        if resp.status_code == 200:
            return resp.json()

        if resp.status_code in (429, 500, 502, 503, 504):
            retry_after = resp.headers.get("Retry-After")

            if retry_after:
                try:
                    sleep_s = float(retry_after)
                except ValueError:
                    sleep_s = backoff
            else:
                sleep_s = backoff

            # Small jitter prevents lockstep retries.
            sleep_s = sleep_s + random.uniform(0, 0.5)

            print(
                f"[WARN] attempt={attempt} status={resp.status_code}; "
                f"sleep={sleep_s:.1f}s url={resp.url}"
            )

            time.sleep(sleep_s)
            backoff = min(backoff * 2, 60)
            continue

        print(f"[FAIL] status={resp.status_code} url={resp.url} body={resp.text[:800]}")
        resp.raise_for_status()

    raise RuntimeError(f"Exhausted {max_attempts} attempts on {url}")


# COMMAND ----------

def discover_active_shipment_ids(token: str, start_date, end_date) -> list[str]:
    """
    Stage 1:
    Use DATE_RANGE endpoint only to discover ShipmentIds that were active/recently updated.

    Important:
    We do NOT use these ItemData rows as final shipment item data because DATE_RANGE can
    omit older SKU lines from still-active shipments.
    """
    url = f"{SP_API_BASE}/fba/inbound/v0/shipmentItems"
    headers = {
        "x-amz-access-token": token,
        "Content-Type": "application/json",
    }

    params = {
        "MarketplaceId": MARKETPLACE_ID,
        "QueryType": "DATE_RANGE",
        "LastUpdatedAfter": start_date.isoformat(),
        "LastUpdatedBefore": end_date.isoformat(),
        "ShipmentStatusList": (
            "WORKING,READY_TO_SHIP,SHIPPED,RECEIVING,CANCELLED,DELETED,"
            "CLOSED,ERROR,IN_TRANSIT,DELIVERED,CHECKED_IN"
        ),
    }

    shipment_ids = set()
    page = 0

    while True:
        body = fetch_with_retry(url, headers, params=params)
        payload = body.get("payload", {}) or {}
        items = payload.get("ItemData", []) or []

        for it in items:
            sid = it.get("ShipmentId")
            if sid:
                shipment_ids.add(sid)

        print(
            f"[INFO] discovery page={page} "
            f"items={len(items)} cum_shipments={len(shipment_ids)}"
        )

        nxt = payload.get("NextToken")
        if not nxt:
            break

        # This endpoint DOES use QueryType=NEXT_TOKEN.
        params = {
            "MarketplaceId": MARKETPLACE_ID,
            "QueryType": "NEXT_TOKEN",
            "NextToken": nxt,
        }

        page += 1

        # Light throttle for discovery pagination.
        time.sleep(0.3)

    return sorted(shipment_ids)


# COMMAND ----------

def fetch_items_for_shipment(token: str, shipment_id: str) -> list[dict]:
    """
    Stage 2:
    Pull the full item list for one shipment.

    Important:
    This is intentionally single-page.
    Do NOT paginate this endpoint with NextToken.
    Testing showed single call returns the expected full SKU list, while NextToken pagination
    can repeat the same 20 rows many times and trigger 429 throttling.
    """
    url = f"{SP_API_BASE}/fba/inbound/v0/shipments/{shipment_id}/items"
    headers = {
        "x-amz-access-token": token,
        "Content-Type": "application/json",
    }

    body = fetch_with_retry(url, headers, params=None)
    payload = body.get("payload", {}) or {}
    items = payload.get("ItemData", []) or []

    # Defensive de-dupe at API row level.
    # Main silver grain is shipment_id + seller_sku.
    # Include FNSKU here to avoid accidentally collapsing unusual SKU/FNSKU variants
    # before the silver grain step.
    dedup = {}
    for it in items:
        key = (
            shipment_id,
            it.get("SellerSKU"),
            it.get("FulfillmentNetworkSKU"),
        )
        dedup[key] = it

    return list(dedup.values())


# COMMAND ----------

access_token = get_access_token()

active_ids = discover_active_shipment_ids(
    token=access_token,
    start_date=WINDOW_START,
    end_date=WINDOW_END,
)

print(f"[INFO] discovered {len(active_ids)} active shipments")

# COMMAND ----------

records = []

for i, sid in enumerate(active_ids):
    items = fetch_items_for_shipment(access_token, sid)

    distinct_skus = len({
        it.get("SellerSKU")
        for it in items
        if it.get("SellerSKU")
    })

    print(
        f"[INFO] [{i + 1}/{len(active_ids)}] {sid}: "
        f"{len(items)} item rows, {distinct_skus} distinct SKUs"
    )

    for it in items:
        records.append((sid, it))

    # Conservative throttle to avoid 429.
    time.sleep(PER_SHIPMENT_SLEEP_SECONDS)

print(f"[INFO] total item rows fetched full per-shipment: {len(records)}")

# COMMAND ----------

# Bronze append — explicit schema.
# raw_payload carries one per-shipment item JSON object.

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
    bronze_rows = [
        (
            RUN_TS.date(),
            RUN_TS,
            WINDOW_START,
            WINDOW_END,
            0,
            json.dumps(it),
            RUN_ID,
        )
        for _, it in records
    ]

    (
        spark.createDataFrame(bronze_rows, schema=BRONZE_SCHEMA)
        .write
        .format("delta")
        .mode("append")
        .saveAsTable(BRONZE)
    )

    print(f"[OK] Bronze appended: {len(bronze_rows)} rows")

else:
    print("[INFO] No items — Bronze unchanged")

# COMMAND ----------

# Silver typed + idempotent MERGE.
# Grain: shipment_id x seller_sku

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
    if v is None:
        return None
    return int(v)


if records:
    silver_rows = [
        (
            sid,
            it.get("SellerSKU"),
            it.get("FulfillmentNetworkSKU"),
            _as_int(it.get("QuantityShipped")),
            _as_int(it.get("QuantityReceived")),
            _as_int(it.get("QuantityInCase")),
            json.dumps(it.get("PrepDetailsList")) if it.get("PrepDetailsList") else None,
            RUN_ID,
            RUN_TS,
        )
        for sid, it in records
    ]

    silver_df = spark.createDataFrame(silver_rows, schema=SILVER_SCHEMA)

    bad = (
        silver_df
        .filter(F.col("shipment_id").isNull() | F.col("seller_sku").isNull())
        .count()
    )

    if bad > 0:
        raise AssertionError(f"[FAIL] {bad} rows with NULL grain key")

    total_rows = silver_df.count()
    distinct_grain_rows = (
        silver_df
        .select("shipment_id", "seller_sku")
        .distinct()
        .count()
    )

    print(f"[PASS] DQ — {total_rows} rows have grain keys")
    print(f"[INFO] silver staging distinct grain rows: {distinct_grain_rows}")

    # Final de-dupe at silver grain.
    # If duplicate shipment_id + seller_sku exists, keep the newest row in this run.
    silver_dedup = (
        silver_df
        .withColumn(
            "_rn",
            F.row_number().over(
                Window
                .partitionBy("shipment_id", "seller_sku")
                .orderBy(F.col("_silver_ingested_at").desc())
            )
        )
        .filter(F.col("_rn") == 1)
        .drop("_rn")
    )

    silver_dedup.createOrReplaceTempView("_stg_items")

    spark.sql(f"""
        MERGE INTO {SILVER} t
        USING _stg_items s
        ON t.shipment_id = s.shipment_id
           AND t.seller_sku = s.seller_sku
        WHEN MATCHED THEN UPDATE SET *
        WHEN NOT MATCHED THEN INSERT *
    """)

    print("[OK] Silver MERGE complete")

else:
    print("[INFO] No items — Silver unchanged")

# COMMAND ----------

display(spark.sql(f"""
    SELECT COUNT(*) AS silver_rows
    FROM {SILVER}
"""))

display(spark.sql(f"""
    SELECT *
    FROM {SILVER}
    ORDER BY _silver_ingested_at DESC
    LIMIT 20
"""))

print(f"\n[OK] Run {RUN_ID} — {len(records)} items processed into {SILVER}")

# COMMAND ----------

# Optional validation for the known shipment that previously had missing SKUs.
# This should return 20 rows / 20 distinct SKUs after the MERGE.

VALIDATION_SHIPMENT_ID = "FBA19CRBL6RZ"

display(spark.sql(f"""
    SELECT
        shipment_id,
        COUNT(*) AS item_rows,
        COUNT(DISTINCT seller_sku) AS distinct_skus
    FROM {SILVER}
    WHERE shipment_id = '{VALIDATION_SHIPMENT_ID}'
    GROUP BY shipment_id
"""))

display(spark.sql(f"""
    SELECT
        shipment_id,
        seller_sku,
        fulfillment_network_sku,
        quantity_shipped,
        quantity_received,
        quantity_in_case,
        _bronze_run_id,
        _silver_ingested_at
    FROM {SILVER}
    WHERE shipment_id = '{VALIDATION_SHIPMENT_ID}'
    ORDER BY seller_sku
"""))

# COMMAND ----------

# Bronze retention — drop partitions older than 90 days.

cutoff = (datetime.now(timezone.utc).date() - timedelta(days=90)).isoformat()

spark.sql(f"""
    DELETE FROM {BRONZE}
    WHERE ingestion_date < DATE'{cutoff}'
""")

print(f"[OK] Bronze retention applied: dropped partitions before {cutoff}")