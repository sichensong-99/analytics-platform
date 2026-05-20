-- =============================================================================
-- Reconciliation Query 1 — New Platform (Databricks SQL)
-- =============================================================================
-- Purpose : Aggregate fact_orders_line by (iso_week × style × channel) for
--           reconciliation against the legacy Panoply Style_selling_dfNEW.
-- Output  : CSV with columns: iso_year, iso_week, vend_id, legacy_channel_group, qty_new
-- Where   : Run in Databricks SQL Editor (or any tool with Databricks SQL connection).
-- When    : Day 5 of slice 1 build, after fact_orders_line is loaded.
-- =============================================================================
--
-- HOW TO RUN
-- ----------
-- 1. Open Databricks SQL Editor in your workspace
-- 2. Paste this entire file
-- 3. Run (Shift + Enter or click Run)
-- 4. Click "Download" → choose CSV
-- 5. Save the file as docs/reconciliation/data/new_platform.csv
--    (the run_reconciliation.py script reads from this path)
--
-- TUNING
-- ------
-- Default window: last 7 complete days (yesterday going back 7 days, today excluded).
-- To change the window, edit the WHERE clause below.
-- =============================================================================

SELECT
    d.iso_year,
    d.iso_week,
    p.vend_id,
    c.legacy_channel_group,
    SUM(f.quantity) AS qty_new
FROM mvdevdatabricks.analytics_platform_32degrees.fact_orders_line f
JOIN mvdevdatabricks.analytics_platform_32degrees.dim_date    d ON f.date_key    = d.date_key
JOIN mvdevdatabricks.analytics_platform_32degrees.dim_product p ON f.product_key = p.product_key
JOIN mvdevdatabricks.analytics_platform_32degrees.dim_channel c ON f.channel_key = c.channel_key
WHERE d.full_date BETWEEN current_date() - INTERVAL 8 DAYS
                      AND current_date() - INTERVAL 1 DAY
  -- Exclude unresolved keys to focus on real reconciliation (orphan rows are a
  -- separate DQ concern handled by notebook 04's multi-tier checks)
  AND p.product_key  > 0
  AND c.channel_key  > 0
GROUP BY ALL
ORDER BY d.iso_year, d.iso_week, p.vend_id, c.legacy_channel_group;
