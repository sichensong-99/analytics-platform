-- =============================================================================
-- Reconciliation Query 1 — New Platform (Databricks SQL)
-- =============================================================================
-- Grain  : iso_year × iso_week × vend_id
-- Window : 2025-07-07 .. 2025-07-13 (fixed)
-- Output : CSV columns: iso_year, iso_week, vend_id, qty_new
--
-- ORDER-TYPE FILTER (approximate legacy-parity)
-- ---------------------------------------------
-- The legacy Panoply report excludes 4 order classes from channel-driven
-- sales: replacements, refunds, exchanges (%EXC%), and Returnly-tagged returns.
-- Rationale (per Leader): refund/replacement are independent post-order events,
-- not channel-attributable sales; including them double-counts or deflates.
--
-- This query approximates that exclusion with the two signals available in
-- fact_orders_line today: %EXC% order names + is_refunded flag.
-- NOT YET COVERED: replacement orders, Returnly-tagged returns — these require
-- source tables / Shopify `tags` not yet ingested via Fivetran. Tracked as a
-- backlog item: materialize a unified `is_sales_attributable` flag (see README).
-- =============================================================================

SELECT
    f.iso_year,
    f.iso_week,
    p.vend_id,
    SUM(f.quantity) AS qty_new
FROM mvdevdatabricks.analytics_platform_32degrees.fact_orders_line f
JOIN mvdevdatabricks.analytics_platform_32degrees.dim_date    d ON f.date_key    = d.date_key
JOIN mvdevdatabricks.analytics_platform_32degrees.dim_product p ON f.product_key = p.product_key
WHERE d.date_actual BETWEEN '2025-07-07' AND '2025-07-13'
  AND p.product_key > 0
  AND f.is_refunded = FALSE
  AND f.shopify_order_name NOT LIKE '%EXC%'
GROUP BY f.iso_year, f.iso_week, p.vend_id
ORDER BY f.iso_year, f.iso_week, p.vend_id;