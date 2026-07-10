# Databricks notebook source
# MAGIC %md
# MAGIC # GA4 Web Analytics Ingestion (Data API → Lakehouse)
# MAGIC
# MAGIC Daily pull of GA4 web-analytics into `analytics_catalog.analytics_platform`
# MAGIC (independent **web-analytics domain**, prefix `ga4_`).
# MAGIC
# MAGIC Reuses the Amazon SP-API ingestion pattern: service-account OAuth, pagination,
# MAGIC quota-aware backoff, medallion (**bronze append / silver MERGE**), incremental
# MAGIC window + full-refresh switch.
# MAGIC
# MAGIC ### Why three reports?
# MAGIC GA4 enforces dimension/metric **scope compatibility** — session-, page-, and
# MAGIC item-scoped fields cannot be mixed in one `runReport`. The required field list is
# MAGIC therefore split into three scope-aligned pulls, each its own silver table at its
# MAGIC natural grain.
# MAGIC
# MAGIC | report  | scope   | grain                              | fields |
# MAGIC |---------|---------|------------------------------------|--------|
# MAGIC | traffic | session | date × landing_page × channel      | sessions, bounce_rate, purchases, revenue |
# MAGIC | page    | page    | date × page_path                   | page_views, add_to_carts |
# MAGIC | item    | item    | date × item_id × item_name         | items_viewed, items_added_to_cart, items_purchased, item_revenue |

# COMMAND ----------
# MAGIC %md ## 0. Install GA4 client + restart Python

# COMMAND ----------
# %pip install + restartPython clears all state, so config/imports live in later cells.
%pip install --quiet google-analytics-data
dbutils.library.restartPython()

# COMMAND ----------
# MAGIC %md ## 1. Config & run-mode widgets

# COMMAND ----------
dbutils.widgets.dropdown("full_refresh", "false", ["false", "true"], "Full refresh (backfill)?")
dbutils.widgets.text("backfill_start_date", "2024-01-01", "Backfill start (YYYY-MM-DD)")
dbutils.widgets.text("lookback_days", "3", "Incremental lookback (days)")
# Property ID is not a secret, but it is a company-internal id — blank this default
# before committing to the public repo (Decision 49).
dbutils.widgets.text("ga4_property_id", "123456789", "GA4 Property ID")

GA4_PROPERTY_ID = dbutils.widgets.get("ga4_property_id")
SECRET_SCOPE    = "ga4"
SECRET_KEY      = "sa_key_json"

CATALOG = "analytics_catalog"
SCHEMA  = "analytics_platform"
BRONZE_TABLE = f"{CATALOG}.{SCHEMA}.ga4_bronze_raw"

FULL_REFRESH   = dbutils.widgets.get("full_refresh") == "true"
BACKFILL_START = dbutils.widgets.get("backfill_start_date")
LOOKBACK_DAYS  = int(dbutils.widgets.get("lookback_days"))

# GA4 finalizes recent data over ~24-48h, so re-pull a small lookback window each run
# and MERGE (idempotent) so late-arriving figures get corrected. "yesterday" = newest
# reasonably-complete day.
if FULL_REFRESH:
    START_DATE, END_DATE = BACKFILL_START, "yesterday"
else:
    START_DATE, END_DATE = f"{LOOKBACK_DAYS}daysAgo", "yesterday"

print(f"Mode = {'FULL_REFRESH' if FULL_REFRESH else 'INCREMENTAL'} | window {START_DATE} -> {END_DATE} | property {GA4_PROPERTY_ID}")

# COMMAND ----------
# MAGIC %md ## 2. Report definitions (scope-aligned)
# MAGIC Field API names validated against the GA4 Data API schema. Kept here as config so a
# MAGIC name fix is one line. `rename` maps GA4 field names → snake_case business columns.

# COMMAND ----------
REPORTS = {
    "traffic": {  # session-scoped: landing page x channel
        "silver_table": f"{CATALOG}.{SCHEMA}.ga4_silver_traffic",
        "dimensions": ["date", "landingPagePlusQueryString", "sessionDefaultChannelGroup"],
        "metrics":    ["sessions", "bounceRate", "ecommercePurchases", "purchaseRevenue"],
        "rename": {
            "landingPagePlusQueryString": "landing_page",
            "sessionDefaultChannelGroup": "channel_group",
            "bounceRate": "bounce_rate",
            "ecommercePurchases": "purchases",
            "purchaseRevenue": "revenue",
        },
        "keys":       ["date", "landing_page", "channel_group"],
        "int_cols":   ["sessions", "purchases"],
        "float_cols": ["bounce_rate", "revenue"],
    },
    "page": {  # page-scoped: page-path engagement
        "silver_table": f"{CATALOG}.{SCHEMA}.ga4_silver_page",
        "dimensions": ["date", "pagePath"],
        "metrics":    ["screenPageViews", "addToCarts"],
        "rename": {
            "pagePath": "page_path",
            "screenPageViews": "page_views",
            "addToCarts": "add_to_carts",
        },
        "keys":       ["date", "page_path"],
        "int_cols":   ["page_views", "add_to_carts"],
        "float_cols": [],
    },
    "item": {  # item-scoped: product funnel (joins to Shopify by product key downstream)
        "silver_table": f"{CATALOG}.{SCHEMA}.ga4_silver_item",
        "dimensions": ["date", "itemId", "itemName"],
        "metrics":    ["itemsViewed", "itemsAddedToCart", "itemsPurchased", "itemRevenue"],
        "rename": {
            "itemId": "item_id",
            "itemName": "item_name",
            "itemsViewed": "items_viewed",
            "itemsAddedToCart": "items_added_to_cart",
            "itemsPurchased": "items_purchased",
            "itemRevenue": "item_revenue",
        },
        "keys":       ["date", "item_id", "item_name"],
        "int_cols":   ["items_viewed", "items_added_to_cart", "items_purchased"],
        "float_cols": ["item_revenue"],
    },
}

# COMMAND ----------
# MAGIC %md ## 3. Authenticate to GA4 Data API (service account from secret scope)

# COMMAND ----------
import json, time, random
from datetime import datetime
from google.oauth2 import service_account
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import DateRange, Dimension, Metric, RunReportRequest
from google.api_core.exceptions import ResourceExhausted, ServiceUnavailable, DeadlineExceeded

raw_key = dbutils.secrets.get(scope=SECRET_SCOPE, key=SECRET_KEY)
sa_info = json.loads(raw_key.encode("utf-8").decode("utf-8-sig"))  # tolerate UTF-8 BOM (Windows)
credentials = service_account.Credentials.from_service_account_info(
    sa_info, scopes=["https://www.googleapis.com/auth/analytics.readonly"]
)
client = BetaAnalyticsDataClient(credentials=credentials)
print(f"Authenticated as: {sa_info.get('client_email')}")  # SA email, not a secret

# COMMAND ----------
# MAGIC %md ## 4. Paginated, quota-aware runReport helper

# COMMAND ----------
PAGE_SIZE   = 100_000   # GA4 hard cap is 250k rows/request; 100k keeps payloads modest
MAX_RETRIES = 5

def _run_with_backoff(request):
    for attempt in range(MAX_RETRIES):
        try:
            return client.run_report(request)
        except (ResourceExhausted, ServiceUnavailable, DeadlineExceeded) as e:
            if attempt == MAX_RETRIES - 1:
                raise
            sleep = min(60, 2 ** attempt) + random.uniform(0, 1)
            print(f"  retry {attempt + 1}/{MAX_RETRIES} after {sleep:.1f}s ({type(e).__name__})")
            time.sleep(sleep)

def run_ga4_report(dimensions, metrics, start_date, end_date):
    """Returns list[dict] {field_name: raw_string_value}, paginating over all rows."""
    out, offset = [], 0
    while True:
        req = RunReportRequest(
            property=f"properties/{GA4_PROPERTY_ID}",
            dimensions=[Dimension(name=d) for d in dimensions],
            metrics=[Metric(name=m) for m in metrics],
            date_ranges=[DateRange(start_date=start_date, end_date=end_date)],
            limit=PAGE_SIZE,
            offset=offset,
        )
        resp = _run_with_backoff(req)
        dim_hdr = [h.name for h in resp.dimension_headers]
        met_hdr = [h.name for h in resp.metric_headers]
        for row in resp.rows:
            rec = {dim_hdr[i]: row.dimension_values[i].value for i in range(len(dim_hdr))}
            rec.update({met_hdr[i]: row.metric_values[i].value for i in range(len(met_hdr))})
            out.append(rec)
        total = resp.row_count or 0
        offset += PAGE_SIZE
        if offset >= total or not resp.rows:
            break
    return out

# COMMAND ----------
# MAGIC %md ## 5. Medallion writers (bronze append, silver MERGE)

# COMMAND ----------
from pyspark.sql import functions as F
from pyspark.sql.types import StructType, StructField, StringType, TimestampType
from delta.tables import DeltaTable

# One raw, append-only audit table for all reports (schema-on-read: payload is JSON).
BRONZE_SCHEMA = StructType([
    StructField("report_name", StringType()),
    StructField("payload",     StringType()),   # raw GA4 row as JSON
    StructField("_ingested_at", TimestampType()),
])

def write_bronze(report_name, rows):
    now = datetime.utcnow()
    data = [(report_name, json.dumps(r), now) for r in rows]
    (spark.createDataFrame(data, BRONZE_SCHEMA)
        .write.format("delta").mode("append").option("mergeSchema", "true")
        .saveAsTable(BRONZE_TABLE))

def _typed_silver_df(rows, cfg):
    if not rows:
        return None
    df = spark.createDataFrame(rows)                      # all string columns
    for src, dst in cfg["rename"].items():                # GA4 names -> snake_case
        if src in df.columns:
            df = df.withColumnRenamed(src, dst)
    df = df.withColumn("date", F.to_date(F.col("date"), "yyyyMMdd"))   # "20260614" -> DATE
    for c in cfg["int_cols"]:
        df = df.withColumn(c, F.col(c).cast("long"))
    for c in cfg["float_cols"]:
        df = df.withColumn(c, F.col(c).cast("double"))
    return df.withColumn("_loaded_at", F.lit(datetime.utcnow()).cast("timestamp"))

def merge_silver(rows, cfg, full_refresh):
    df = _typed_silver_df(rows, cfg)
    table = cfg["silver_table"]
    if df is None:
        print(f"  {table}: 0 rows pulled, skipping")
        return 0
    if full_refresh:
        (df.write.format("delta").mode("overwrite")
            .option("overwriteSchema", "true").saveAsTable(table))
    elif not spark.catalog.tableExists(table):
        df.write.format("delta").saveAsTable(table)
    else:
        tgt = DeltaTable.forName(spark, table)
        cond = " AND ".join([f"t.{k} <=> s.{k}" for k in cfg["keys"]])  # null-safe match
        (tgt.alias("t").merge(df.alias("s"), cond)
            .whenMatchedUpdateAll().whenNotMatchedInsertAll().execute())
    return df.count()

# COMMAND ----------
# MAGIC %md ## 6. Run all reports

# COMMAND ----------
summary = {}
for name, cfg in REPORTS.items():
    print(f"\n=== {name} ===")
    rows = run_ga4_report(cfg["dimensions"], cfg["metrics"], START_DATE, END_DATE)
    print(f"  pulled {len(rows):,} rows from GA4")
    write_bronze(name, rows)
    n = merge_silver(rows, cfg, FULL_REFRESH)
    summary[name] = {"pulled": len(rows), "table": cfg["silver_table"]}

print("\n--- DONE ---")
for k, v in summary.items():
    print(f"{k:8s} pulled={v['pulled']:>9,}  -> {v['table']}")

# COMMAND ----------
# MAGIC %md ## 7. Sanity check (row counts + freshness per silver table)

# COMMAND ----------
checks = []
for name, cfg in REPORTS.items():
    t = cfg["silver_table"]
    if spark.catalog.tableExists(t):
        r = spark.sql(
            f"SELECT COUNT(*) c, MIN(date) mn, MAX(date) mx FROM {t}"
        ).collect()[0]
        checks.append((name, t, r["c"], str(r["mn"]), str(r["mx"])))
display(spark.createDataFrame(checks, ["report", "table", "rows", "min_date", "max_date"]))