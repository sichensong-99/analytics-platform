# Databricks notebook source
# 06_build_cohort
# Customer cohort + new/returning modeling off shopify_raw.order.
# Window functions (ROW_NUMBER per customer) derive first-order vs repeat;
# first-order month = cohort; retention = distinct active customers per period.
# Writes two governed Delta tables the metrics-service can read.

# COMMAND ----------

SCHEMA = "analytics_catalog.analytics_platform"

# Valid purchase events + per-customer order sequence + cohort month.
spark.sql(f"""
CREATE OR REPLACE TEMP VIEW cohort_seq AS
WITH valid_orders AS (
  SELECT
    customer_id,
    id                                   AS order_id,
    created_at,
    date_trunc('MONTH', created_at)      AS order_month,
    total_price
  FROM analytics_catalog.shopify_raw.order
  WHERE customer_id IS NOT NULL
    AND created_at IS NOT NULL
    AND cancelled_at IS NULL
    AND COALESCE(test, false) = false
    AND COALESCE(_fivetran_deleted, false) = false
    AND COALESCE(financial_status, '') NOT IN ('refunded', 'voided')
)
SELECT
  *,
  ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY created_at, order_id) AS order_seq,
  MIN(date_trunc('MONTH', created_at)) OVER (PARTITION BY customer_id)       AS cohort_month
FROM valid_orders
""")

# COMMAND ----------

# Table 1 — new vs returning, by month.
spark.sql(f"""
CREATE OR REPLACE TABLE {SCHEMA}.cohort_orders_monthly AS
SELECT
  order_month,
  COUNT(CASE WHEN order_seq = 1 THEN 1 END)                              AS new_orders,
  COUNT(CASE WHEN order_seq > 1 THEN 1 END)                              AS returning_orders,
  ROUND(SUM(CASE WHEN order_seq = 1 THEN total_price ELSE 0 END), 2)     AS new_revenue,
  ROUND(SUM(CASE WHEN order_seq > 1 THEN total_price ELSE 0 END), 2)     AS returning_revenue
FROM cohort_seq
GROUP BY order_month
ORDER BY order_month
""")

# COMMAND ----------

# Table 2 — cohort retention matrix (cohort_month x months-since-first).
spark.sql(f"""
CREATE OR REPLACE TABLE {SCHEMA}.cohort_retention AS
WITH activity AS (
  SELECT DISTINCT
    customer_id,
    cohort_month,
    CAST(months_between(order_month, cohort_month) AS INT) AS period_index
  FROM cohort_seq
),
sizes AS (
  SELECT cohort_month, COUNT(DISTINCT customer_id) AS cohort_size
  FROM activity
  WHERE period_index = 0
  GROUP BY cohort_month
)
SELECT
  a.cohort_month,
  a.period_index,
  COUNT(DISTINCT a.customer_id)                              AS active_customers,
  s.cohort_size,
  ROUND(COUNT(DISTINCT a.customer_id) / s.cohort_size, 4)    AS retention_rate
FROM activity a
JOIN sizes s ON a.cohort_month = s.cohort_month
GROUP BY a.cohort_month, a.period_index, s.cohort_size
ORDER BY a.cohort_month, a.period_index
""")

# COMMAND ----------

print("cohort_orders_monthly:")
display(spark.sql(f"SELECT * FROM {SCHEMA}.cohort_orders_monthly ORDER BY order_month DESC LIMIT 12"))
print("cohort_retention (recent cohorts, first periods):")
display(spark.sql(f"""
  SELECT * FROM {SCHEMA}.cohort_retention
  WHERE period_index <= 6 AND cohort_month >= add_months(current_date(), -12)
  ORDER BY cohort_month DESC, period_index
"""))