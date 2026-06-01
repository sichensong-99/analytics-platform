-- ============================================================================
-- Reconciliation Query 1 — New Platform (Databricks)
-- ============================================================================
-- Grain  : iso_year x iso_week x vend_id   (matches 02_panoply_legacy_query.sql)
-- Output : CSV columns: iso_year, iso_week, vend_id, qty_new
-- Window : ISO 2025-W28  (= 2025-07-07 .. 2025-07-13, matches query 2)
-- Model  : Decision 22 v3 —
--          * EXC + replacement excluded via is_sales_attributable = TRUE
--          * refunds netted line-level: net units = quantity - refunded_quantity
--          * vend_id IS NOT NULL mirrors Panoply (drops ERS-unmatched lines)
-- ============================================================================

SELECT
    f.iso_year,
    f.iso_week,
    p.vend_id,
    SUM(f.quantity - f.refunded_quantity) AS qty_new
FROM mvdevdatabricks.analytics_platform_32degrees.fact_orders_line AS f
JOIN mvdevdatabricks.analytics_platform_32degrees.dim_product AS p
    ON f.product_key = p.product_key
WHERE f.iso_year = 2025
  AND f.iso_week = 28
  AND f.is_sales_attributable = TRUE
  AND p.vend_id IS NOT NULL
GROUP BY f.iso_year, f.iso_week, p.vend_id
ORDER BY f.iso_year, f.iso_week, p.vend_id;