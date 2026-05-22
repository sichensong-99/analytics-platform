-- =============================================================================
-- Reconciliation Query 2 — Legacy Panoply (Redshift)
-- =============================================================================
-- Grain  : iso_year × iso_week × vend_id   (matches query 1)
-- Output : CSV columns: iso_year, iso_week, vend_id, qty_panoply
-- Window : 2025-07-07 .. 2025-07-13 (same as query 1)
-- Run    : Panoply SQL Editor → Export as CSV →
--          save as docs/reconciliation/data/panoply_legacy.csv
-- Notes  : Panoply `style` column = new platform `vend_id`.
--          ISO week recomputed from `day` via Redshift TO_CHAR (Decision 11).
-- =============================================================================

SELECT
    TO_CHAR(day, 'IYYY')::INT AS iso_year,
    TO_CHAR(day, 'IW')::INT   AS iso_week,
    style                     AS vend_id,
    SUM(quantity)             AS qty_panoply
FROM "Style_selling_dfNEW"
WHERE day BETWEEN '2025-07-07' AND '2025-07-13'
  AND quantity IS NOT NULL
  AND style IS NOT NULL
GROUP BY 1, 2, 3
ORDER BY 1, 2, 3;