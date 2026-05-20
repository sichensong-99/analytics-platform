-- =============================================================================
-- Reconciliation Query 2 — Legacy Panoply (Redshift / PostgreSQL flavor)
-- =============================================================================
-- Purpose : Aggregate Style_selling_dfNEW by (iso_week × style × channel) for
--           reconciliation against the new platform fact_orders_line.
-- Output  : CSV with columns: iso_year, iso_week, vend_id, legacy_channel_group, qty_panoply
-- Where   : Run in Panoply Web UI SQL Editor.
-- When    : Day 5 of slice 1 build, same time window as query 1.
-- =============================================================================
--
-- HOW TO RUN
-- ----------
-- 1. Open Panoply Web UI
-- 2. Open SQL Editor (Query tab)
-- 3. Paste this entire file
-- 4. Run
-- 5. Click "Export" or "Download" → choose CSV
-- 6. Save the file as docs/reconciliation/data/panoply_legacy.csv
--    (the run_reconciliation.py script reads from this path)
--
-- KEY DESIGN NOTES
-- ----------------
-- 1. We do NOT use Style_selling_dfNEW's native `year` and `week` columns because
--    they may follow US-week (Sunday-start) semantics rather than ISO 8601. Instead
--    we recompute ISO 8601 weeks from the `day` column to match the new platform's
--    dim_date semantics (Decision 11: ISO 8601 only). This ensures apples-to-apples
--    comparison.
--
-- 2. The column name `style` in Style_selling_dfNEW maps to vend_id in the new
--    dim_product. We rename it here to vend_id so the CSV is directly joinable.
--
-- 3. The column `channelgrouping` is GA4-style channel grouping ("Paid Search",
--    "Email", "Organic Search", etc.). This matches the new dim_channel's
--    legacy_channel_group column by design (Decision 15: dual-display dimension).
-- =============================================================================

SELECT
    EXTRACT(ISOYEAR FROM day)::INT  AS iso_year,
    EXTRACT(WEEK    FROM day)::INT  AS iso_week,
    style                            AS vend_id,
    channelgrouping                  AS legacy_channel_group,
    SUM(quantity)                    AS qty_panoply
FROM "Style_selling_dfNEW"
WHERE day BETWEEN (CURRENT_DATE - INTERVAL '8 days')
              AND (CURRENT_DATE - INTERVAL '1 day')
  AND quantity IS NOT NULL
  AND style IS NOT NULL
  AND channelgrouping IS NOT NULL
GROUP BY 1, 2, 3, 4
ORDER BY 1, 2, 3, 4;

-- =============================================================================
-- POTENTIAL DIALECT TROUBLESHOOTING
-- =============================================================================
-- If Panoply returns errors on EXTRACT(ISOYEAR / WEEK ...), try these alternatives:
--
--   Redshift native ISO 8601 week:
--     TO_CHAR(day, 'IYYY')::INT  AS iso_year
--     TO_CHAR(day, 'IW')::INT    AS iso_week
--
--   Or compute via date_trunc:
--     EXTRACT(YEAR FROM date_trunc('week', day))::INT  AS iso_year  -- approximate
--     -- Then use a CASE to handle cross-year boundaries
--
-- If your Panoply schema requires explicit schema prefix:
--   FROM public."Style_selling_dfNEW"
-- =============================================================================
