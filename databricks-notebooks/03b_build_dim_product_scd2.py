# Databricks notebook source
# MAGIC %md
# MAGIC # Slice 1 — Notebook 03b: Build `dim_product_scd2` (SCD Type 2)
# MAGIC
# MAGIC **Purpose**: Maintain a Slowly-Changing-Dimension **Type 2** history of the
# MAGIC product master, so analysis can ask "what were this product's attributes
# MAGIC *as of* the order date" (point-in-time), not just "what are they now".
# MAGIC
# MAGIC **Why a SEPARATE table (not in-place upgrade of `dim_product`)**:
# MAGIC - `dim_product` (SCD1) is the durable current-state dimension that
# MAGIC   `fact_orders_line` already joins on `product_key`, and that fact is
# MAGIC   **already reconciled** against the legacy baseline (1.69%). Changing
# MAGIC   `product_key` semantics in place would fan-out / break that join and
# MAGIC   force a re-reconciliation. So we keep `dim_product` untouched and add
# MAGIC   `dim_product_scd2` purely additively.
# MAGIC - Downstream (fact joins, metrics) require **zero** changes.
# MAGIC - Point-in-time is resolved at query time by bridging
# MAGIC   `fact -> dim_product (sku) -> dim_product_scd2 (date range)`.
# MAGIC
# MAGIC **Source**: `analytics_platform.dim_product` (the curated SCD1
# MAGIC snapshot — ERS read / dual-schema detection / sentinel fill / de-dup all
# MAGIC live in notebook 03, so they are maintained in ONE place).
# MAGIC **Output**: `analytics_platform.dim_product_scd2` + view
# MAGIC `vw_dim_product_current`.
# MAGIC
# MAGIC **Type-2 tracked attributes**: all descriptive ERS attributes (any change
# MAGIC opens a new version). `sku` = natural key (never changes). `is_complete`
# MAGIC = derived DQ flag, recomputed per version, NOT part of change detection.
# MAGIC
# MAGIC **History start**: from the current snapshot (today = version 1). Real
# MAGIC history accrues going forward. (Could be back-filled later by replaying
# MAGIC monthly ERS CSVs in chronological order — out of scope, YAGNI for now.)
# MAGIC
# MAGIC **Idempotent**: Yes — re-running with an unchanged source is a no-op
# MAGIC (hash match → nothing staged).
# MAGIC
# MAGIC **Author**: Sia Song
# MAGIC **Created**: 2026-06-16  (Decision 56 — upgrades the SCD1 of Decision 12)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Configuration

# COMMAND ----------

TARGET_CATALOG = "analytics_catalog"
TARGET_SCHEMA  = "analytics_platform"

SOURCE_TABLE = f"{TARGET_CATALOG}.{TARGET_SCHEMA}.dim_product"          # curated SCD1 current snapshot
TARGET_TABLE = f"{TARGET_CATALOG}.{TARGET_SCHEMA}.dim_product_scd2"     # SCD2 history (this notebook)
CURRENT_VIEW = f"{TARGET_CATALOG}.{TARGET_SCHEMA}.vw_dim_product_current"

# Attributes whose change opens a new SCD2 version (Type-2).
# NOT included: sku (natural key, Type-0), is_complete (derived DQ flag),
# and the _ers_schema_version / _ingested_at provenance columns.
SCD2_TRACKED_COLS = [
    "vend_id", "item_description", "season", "group_name",
    "gender", "class_name", "master_style", "cost", "retail",
]

# Open-ended "current" sentinel. Using a high date instead of NULL keeps
# range joins (effective_from <= d < effective_to) simple — no NULL handling.
HIGH_DATE = "9999-12-31 00:00:00"
LOW_DATE  = "1900-01-01 00:00:00"   # Unknown member's effective_from

print(f"[INFO] Source : {SOURCE_TABLE}")
print(f"[INFO] Target : {TARGET_TABLE}")
print(f"[INFO] Tracked: {SCD2_TRACKED_COLS}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Helpers — row_hash + reusable SCD2 merge function
# MAGIC
# MAGIC `apply_scd2_merge` is the core. It implements SCD2 via a single atomic
# MAGIC Delta `MERGE` plus the **merge-key trick**: a changed natural key is staged
# MAGIC TWICE — once with its real key (matches the live row → expire it) and once
# MAGIC with a NULL key (never matches → insert the new version).

# COMMAND ----------

from pyspark.sql import functions as F
from pyspark.sql import DataFrame
from pyspark.sql.window import Window
from delta.tables import DeltaTable


def add_row_hash(df: DataFrame, cols: list) -> DataFrame:
    """Null-safe SHA-256 over the tracked attributes (NULL gets a sentinel so
    NULL and '' don't collide)."""
    hash_input = F.concat_ws(
        "||",
        *[F.coalesce(F.col(c).cast("string"), F.lit("<NULL>")) for c in cols],
    )
    return df.withColumn("row_hash", F.sha2(hash_input, 256))


def create_scd2_table(fqn: str) -> None:
    """Create the SCD2 table if it doesn't exist (used for prod + the demo)."""
    spark.sql(f"""
        CREATE TABLE IF NOT EXISTS {fqn} (
          product_version_key  BIGINT,
          sku                  STRING,
          vend_id              STRING,
          item_description     STRING,
          season               STRING,
          group_name           STRING,
          gender               STRING,
          class_name           STRING,
          master_style         STRING,
          cost                 DECIMAL(10,2),
          retail               DECIMAL(10,2),
          is_complete          BOOLEAN,
          row_hash             STRING,
          effective_from       TIMESTAMP,
          effective_to         TIMESTAMP,
          is_current           BOOLEAN,
          _ers_schema_version  STRING,
          _ingested_at         TIMESTAMP
        ) USING DELTA
        COMMENT 'SCD Type 2 product dimension (history). Current-state lives in dim_product (SCD1, untouched). Source = dim_product.'
    """)


def seed_unknown_member(fqn: str) -> None:
    """Kimball Unknown member at product_version_key = 0, open all-time.
    Inserted once (only when the table is empty)."""
    if spark.table(fqn).count() == 0:
        spark.sql(f"""
            INSERT INTO {fqn} VALUES (
              0, '__UNKNOWN__', 'UNKNOWN', 'Unknown Product', 'UNKNOWN', 'UNKNOWN',
              'UNKNOWN', 'UNKNOWN', 'UNKNOWN', CAST(NULL AS DECIMAL(10,2)), CAST(NULL AS DECIMAL(10,2)),
              false, 'UNKNOWN_MEMBER',
              TIMESTAMP'{LOW_DATE}', TIMESTAMP'{HIGH_DATE}', true,
              'unknown_member', current_timestamp()
            )
        """)
        print(f"[INFO] Seeded Unknown member (product_version_key = 0) into {fqn}")


def apply_scd2_merge(target_fqn: str, source_df: DataFrame,
                     tracked_cols: list, run_ts) -> dict:
    """
    SCD Type 2 upsert via Delta MERGE + the merge-key trick.

    `source_df` = one row per natural key (sku) for the CURRENT snapshot,
    carrying the tracked attrs + is_complete + _ers_schema_version (no SCD2
    control columns — those are added here).
    """
    target = DeltaTable.forName(spark, target_fqn)
    target_df = target.toDF()

    # Live (current) versions in the target — real members only.
    current = (
        target_df.filter(F.col("is_current") == True)  # noqa: E712
                 .select("sku", F.col("row_hash").alias("tgt_hash"))
    )

    # Hash the incoming snapshot, then classify each sku.
    src = add_row_hash(source_df, tracked_cols)
    joined = src.join(current, on="sku", how="left")

    new_rows     = joined.filter(F.col("tgt_hash").isNull())                       # sku not live in target
    changed_rows = joined.filter(
        F.col("tgt_hash").isNotNull() & (F.col("row_hash") != F.col("tgt_hash"))   # live but attrs changed
    )
    # Unchanged (hash matches) → not staged → no-op.

    # Materialize counts BEFORE the merge. If counted AFTER .execute(), these lazy
    # DataFrames would re-read the (now-updated) target and report 0 — a classic
    # Spark lazy-evaluation gotcha. Counting here pins them to the pre-merge snapshot.
    n_new     = new_rows.count()
    n_changed = changed_rows.count()

    # --- rows we will INSERT (new skus + new versions of changed skus) ---
    to_insert = new_rows.unionByName(changed_rows).drop("tgt_hash")

    # Assign fresh surrogate keys above the current max.
    # (Fine for a single-writer batch job; concurrent writers would need an
    #  IDENTITY column or sequence — noted as a trade-off.)
    max_key = target_df.agg(F.max("product_version_key")).first()[0] or 0
    w = Window.orderBy("sku")
    to_insert = (
        to_insert
        .withColumn("product_version_key", F.lit(max_key) + F.row_number().over(w))
        .withColumn("effective_from", F.lit(run_ts).cast("timestamp"))
        .withColumn("effective_to",   F.lit(HIGH_DATE).cast("timestamp"))
        .withColumn("is_current",     F.lit(True))
        .withColumn("_ingested_at",   F.lit(run_ts).cast("timestamp"))
        .withColumn("merge_key",      F.lit(None).cast("string"))   # NULL → never matches → INSERT
    )

    # --- rows that EXPIRE the old live version (changed skus only) ---
    expire = (
        changed_rows.select("sku")
        .withColumn("effective_from", F.lit(run_ts).cast("timestamp"))  # becomes old row's effective_to
        .withColumn("merge_key", F.col("sku"))                          # real key → MATCHES the live row
    )

    # Align expire to the same columns as to_insert (unused ones = typed NULLs).
    insert_cols = to_insert.columns
    insert_dtypes = dict(to_insert.dtypes)
    for c in insert_cols:
        if c not in expire.columns:
            expire = expire.withColumn(c, F.lit(None).cast(insert_dtypes[c]))
    expire = expire.select(insert_cols)

    staged = to_insert.unionByName(expire)

    # Values for the INSERT branch = every target column from src (drop merge_key).
    insert_values = {c: f"src.{c}" for c in insert_cols if c != "merge_key"}

    (
        target.alias("tgt")
        .merge(staged.alias("src"), "tgt.sku = src.merge_key AND tgt.is_current = true")
        .whenMatchedUpdate(set={
            "is_current":   "false",
            "effective_to": "src.effective_from",   # old version ends where new one begins (half-open)
        })
        .whenNotMatchedInsert(values=insert_values)
        .execute()
    )

    return {"new": n_new, "changed": n_changed}

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Create target table + Unknown member (idempotent)

# COMMAND ----------

create_scd2_table(TARGET_TABLE)
seed_unknown_member(TARGET_TABLE)
print("[OK] Target ready")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Build the source snapshot (from the curated SCD1 dimension)
# MAGIC
# MAGIC Read `dim_product`, drop its Unknown member (the SCD2 table has its own),
# MAGIC and keep only the natural key + tracked attrs + provenance. No CSV reading
# MAGIC and no normalization here — that already happened upstream in notebook 03.

# COMMAND ----------

source_snapshot = (
    spark.table(SOURCE_TABLE)
         .filter(F.col("product_key") != 0)     # exclude Unknown member
         .select("sku", *SCD2_TRACKED_COLS, "is_complete", "_ers_schema_version")
)

print(f"[INFO] Source snapshot rows: {source_snapshot.count():,}")
source_snapshot.show(5, truncate=False)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Apply the SCD2 merge (production)

# COMMAND ----------

RUN_TS = spark.sql("SELECT current_timestamp()").first()[0]

stats = apply_scd2_merge(TARGET_TABLE, source_snapshot, SCD2_TRACKED_COLS, RUN_TS)

print(f"[OK] SCD2 merge complete")
print(f"     new skus inserted as v1 : {stats['new']:,}")
print(f"     changed skus (old expired + new version inserted): {stats['changed']:,}")
print(f"     (first run: 'new' = full product count, 'changed' = 0)")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6. Validation & integrity checks

# COMMAND ----------

t = spark.table(TARGET_TABLE)

total      = t.count()
distinct   = t.select("sku").distinct().count()
current_ct = t.filter("is_current = true").count()

print(f"[INFO] total rows (all versions) : {total:,}")
print(f"[INFO] distinct skus             : {distinct:,}")
print(f"[INFO] current (is_current=true) : {current_ct:,}")

# INTEGRITY 1: at most one current version per sku
dup_current = (
    t.filter("is_current = true").groupBy("sku").count().filter("count > 1").count()
)
assert dup_current == 0, f"FAIL: {dup_current} sku(s) have >1 current version"

# INTEGRITY 2: every sku has exactly one open (effective_to = HIGH_DATE) version
open_per_sku = (
    t.filter(f"effective_to = TIMESTAMP'{HIGH_DATE}'")
     .groupBy("sku").count()
)
bad_open = open_per_sku.filter("count != 1").count()
assert bad_open == 0, f"FAIL: {bad_open} sku(s) don't have exactly one open version"

# INTEGRITY 3: product_version_key unique
assert t.select("product_version_key").distinct().count() == total, "FAIL: product_version_key not unique"

print("[OK] Integrity checks passed (one current per sku, one open per sku, unique keys)")

# Version distribution (how many skus sit at 1 version, 2 versions, ...)
print("\n[INFO] Version-count distribution per sku:")
(
    t.filter("product_version_key != 0")
     .groupBy("sku").count().withColumnRenamed("count", "versions")
     .groupBy("versions").count().orderBy("versions")
     .show()
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 7. Point-in-time ("as-of") demo
# MAGIC
# MAGIC The whole reason SCD2 exists. Picks a sample sku and shows the version
# MAGIC that was in effect on a given date. After the first run every sku has one
# MAGIC version; this becomes interesting once attributes change over time (see §8).

# COMMAND ----------

SAMPLE_SKU = (
    spark.table(TARGET_TABLE).filter("product_version_key != 0")
         .select("sku").limit(1).first()[0]
)

# Use current_timestamp() so the as-of point is AFTER this run's effective_from.
# A *past* date (e.g. TIMESTAMP'2026-06-16 00:00:00') returns EMPTY — correct
# temporal behaviour: history starts at this run, so the product didn't yet
# "exist" then. Past-date as-of only shows effect once versions accrue (see §8).
print(f"[INFO] Attributes of sku '{SAMPLE_SKU}' as of NOW:")
spark.sql(f"""
    SELECT product_version_key, sku, season, item_description, cost, retail,
           effective_from, effective_to, is_current
    FROM {TARGET_TABLE}
    WHERE sku = '{SAMPLE_SKU}'
      AND current_timestamp() >= effective_from
      AND current_timestamp() <  effective_to
""").show(truncate=False)

# COMMAND ----------

# MAGIC %md
# MAGIC **Template — point-in-time join from a fact (no fact changes needed):**
# MAGIC ```sql
# MAGIC -- Bridges fact -> dim_product (durable current dim, carries sku) -> dim_product_scd2 by date range.
# MAGIC -- Replace <ORDER_DATE_COL> with fact_orders_line's order-date column.
# MAGIC SELECT f.*,
# MAGIC        h.season           AS season_as_of_order,
# MAGIC        h.item_description AS item_desc_as_of_order,
# MAGIC        h.cost             AS cost_as_of_order
# MAGIC FROM analytics_catalog.analytics_platform.fact_orders_line f
# MAGIC JOIN analytics_catalog.analytics_platform.dim_product d
# MAGIC   ON f.product_key = d.product_key                 -- existing SCD1 dim, unchanged
# MAGIC JOIN analytics_catalog.analytics_platform.dim_product_scd2 h
# MAGIC   ON d.sku = h.sku
# MAGIC  AND f.<ORDER_DATE_COL> >= h.effective_from
# MAGIC  AND f.<ORDER_DATE_COL> <  h.effective_to          -- half-open: no double match at boundaries
# MAGIC ```

# COMMAND ----------

# MAGIC %md
# MAGIC ## 8. (Optional) SCD2 behaviour verification — isolated demo table
# MAGIC
# MAGIC Proves the merge-key MERGE really versions a row: build a 1-sku snapshot,
# MAGIC merge it (v1), change `season`, merge again (expires v1, inserts v2).
# MAGIC Runs on a throwaway `_dim_product_scd2_demo` table so production is untouched.
# MAGIC Screenshot the final output for the README / blog.

# COMMAND ----------

DEMO_TABLE = f"{TARGET_CATALOG}.{TARGET_SCHEMA}._dim_product_scd2_demo"
spark.sql(f"DROP TABLE IF EXISTS {DEMO_TABLE}")
create_scd2_table(DEMO_TABLE)
seed_unknown_member(DEMO_TABLE)

demo_cols = ["sku", *SCD2_TRACKED_COLS, "is_complete", "_ers_schema_version"]

def _demo_row(season_val):
    # one fabricated product; only `season` differs between the two loads
    return spark.createDataFrame(
        [("DEMO-001", "DEMOSTYLE", "Demo Jacket", season_val, "Outerwear",
          "Unisex", "Jackets", "DEMO-MASTER", 40.00, 99.00, True, "current")],
        schema=demo_cols,
    )

# Load 1 → version 1 (season = FW25)
s1 = apply_scd2_merge(DEMO_TABLE, _demo_row("FW25"),
                      SCD2_TRACKED_COLS, spark.sql("SELECT timestamp'2026-06-16 09:00:00'").first()[0])
print(f"[DEMO] load 1: {s1}")

# Load 2 → season re-classified to 'Core' → v1 expired, v2 opened
s2 = apply_scd2_merge(DEMO_TABLE, _demo_row("Core"),
                      SCD2_TRACKED_COLS, spark.sql("SELECT timestamp'2026-09-01 09:00:00'").first()[0])
print(f"[DEMO] load 2: {s2}  (expect new=0, changed=1)")

print("\n[DEMO] Full version history for DEMO-001 (note v1 closed, v2 open):")
spark.sql(f"""
    SELECT product_version_key, sku, season, effective_from, effective_to, is_current
    FROM {DEMO_TABLE}
    WHERE sku = 'DEMO-001'
    ORDER BY effective_from
""").show(truncate=False)

print("[DEMO] As-of 2026-07-01 → should return the FW25 version:")
spark.sql(f"""
    SELECT sku, season, effective_from, effective_to
    FROM {DEMO_TABLE}
    WHERE sku = 'DEMO-001'
      AND timestamp'2026-07-01' >= effective_from
      AND timestamp'2026-07-01' <  effective_to
""").show(truncate=False)

# Clean up the throwaway table (comment out if you want to keep it for screenshots)
spark.sql(f"DROP TABLE IF EXISTS {DEMO_TABLE}")
print("[DEMO] dropped demo table")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 9. Current-state view
# MAGIC
# MAGIC Convenience view exposing only the live version of each product, shaped
# MAGIC like the current `dim_product` business columns. Lets anything that wants
# MAGIC "current state" read the SCD2 table without an `is_current` filter.

# COMMAND ----------

spark.sql(f"""
    CREATE OR REPLACE VIEW {CURRENT_VIEW} AS
    SELECT product_version_key, sku, vend_id, item_description, season,
           group_name, gender, class_name, master_style, cost, retail, is_complete
    FROM {TARGET_TABLE}
    WHERE is_current = true
""")
print(f"[OK] Created view {CURRENT_VIEW}")
spark.table(CURRENT_VIEW).show(5, truncate=False)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 10. Summary
# MAGIC
# MAGIC | Item | Value |
# MAGIC |---|---|
# MAGIC | Target | `analytics_platform.dim_product_scd2` |
# MAGIC | Source | `analytics_platform.dim_product` (SCD1, unchanged) |
# MAGIC | SCD type | Type 2 (merge-key trick, single atomic Delta MERGE) |
# MAGIC | Tracked attrs | all descriptive ERS attributes (single `row_hash`) |
# MAGIC | Natural key | `sku` · Surrogate | `product_version_key` |
# MAGIC | Open-end sentinel | `effective_to = 9999-12-31`, half-open ranges |
# MAGIC | Current view | `vw_dim_product_current` (is_current = true) |
# MAGIC | fact_orders_line | **NOT modified** — point-in-time via bridge join |
# MAGIC | Idempotent | Yes (unchanged source → hash match → no-op) |