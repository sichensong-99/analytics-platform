-- ============================================================================
-- Page_view gold — FINAL, materialized at day × product   Decision 54 · option B
-- ----------------------------------------------------------------------------
-- Validated 2025-07-01..09 vs legacy PBI Page_view:
--   • Shopify (unique_orders/units/net): top sellers ~-1%, week-total -2.8%,
--     fully attributed to legacy tag-based refund detection catching only ~45%
--     of refunds (option B nets ALL refunds — more correct, slightly conservative).
--   • Category/Gender/Desc: match (Category = dim_product.group_name).
--   • GA4 event_count/add_to_carts/sessions: ~5-8% lower (Unassigned more) — a
--     GA4 Data API artifact ((other) high-cardinality bucketing + date-tz edge),
--     NOT a logic error. Accepted as directional (work debt; parity not chased).
--
-- Grain: (date, page). Portal filters/aggregates over date ranges.
-- GA4 date vs Shopify ET (-5h) may differ by a boundary day at day-grain; it
-- washes out when the portal sums over a range.
-- ============================================================================

CREATE OR REPLACE TABLE analytics_catalog.analytics_platform.page_view_gold AS
WITH o AS (
    SELECT id AS order_id,
           to_date(processed_at - INTERVAL 5 HOURS) AS et_day
    FROM dpsync.shopify_raw.order
    WHERE COALESCE(_dpsync_deleted, false) = false AND processed_at IS NOT NULL
),
ol AS (
    SELECT id AS order_line_id, order_id, sku, product_id, quantity,
           (COALESCE(price, 0) * quantity - COALESCE(total_discount, 0)) AS net_line
    FROM dpsync.shopify_raw.order_line
    WHERE COALESCE(_dpsync_deleted, false) = false
),
order_qty AS (SELECT order_id, SUM(quantity) AS total_order_qty FROM ol GROUP BY order_id),
refunded_keys AS (
    SELECT DISTINCT ol.order_id, ol.sku
    FROM dpsync.shopify_raw.order_line_refund r
    JOIN ol ON r.order_line_id = ol.order_line_id
    WHERE COALESCE(r._dpsync_deleted, false) = false
),
p AS (SELECT id AS product_id, handle FROM dpsync.shopify_raw.product
      WHERE COALESCE(_dpsync_deleted, false) = false),
sales_lines AS (
    SELECT o.et_day, o.order_id, ol.sku, ol.quantity, ol.net_line,
           CONCAT('/products/', p.handle) AS ga_url
    FROM ol
    JOIN o ON ol.order_id = o.order_id
    JOIN order_qty oq ON ol.order_id = oq.order_id
    LEFT JOIN p ON ol.product_id = p.product_id
    LEFT JOIN refunded_keys rk ON ol.order_id = rk.order_id AND ol.sku = rk.sku
    WHERE ol.net_line <> 0 AND oq.total_order_qty <= 30
      AND p.handle IS NOT NULL AND rk.order_id IS NULL
    -- NOTE: no window here → builds full history. Add an et_day BETWEEN ... to limit.
),
shopify_agg AS (
    SELECT s.et_day AS date, s.ga_url,
           COUNT(DISTINCT s.order_id) AS unique_orders,
           SUM(s.quantity)            AS units_sold,
           ROUND(SUM(s.net_line), 2)  AS net_sales,
           MAX(dp.group_name)         AS category,
           MAX(dp.gender)             AS gender,
           MAX(dp.item_description)   AS descr
    FROM sales_lines s
    LEFT JOIN analytics_catalog.analytics_platform.dim_product dp ON s.sku = dp.sku
    GROUP BY s.et_day, s.ga_url
),
ga4_page AS (
    SELECT date, ga_url, SUM(event_count) AS event_count, SUM(add_to_carts) AS add_to_carts
    FROM (SELECT date, regexp_extract(page_path,'(/products/[^/?#]+)',1) AS ga_url,
                 event_count, add_to_carts
          FROM analytics_catalog.analytics_platform.ga4_silver_page)
    WHERE ga_url <> '' GROUP BY date, ga_url
),
ga4_traffic_pivot AS (
    SELECT date, ga_url,
        SUM(CASE WHEN channel_group='Email'            THEN sessions ELSE 0 END) AS email,
        SUM(CASE WHEN channel_group='Paid Search'      THEN sessions ELSE 0 END) AS paid_search,
        SUM(CASE WHEN channel_group='Paid Social'      THEN sessions ELSE 0 END) AS paid_social,
        SUM(CASE WHEN channel_group='Affiliates'       THEN sessions ELSE 0 END) AS affiliates,
        SUM(CASE WHEN channel_group='Organic Social'   THEN sessions ELSE 0 END) AS organic_social,
        SUM(CASE WHEN channel_group='Direct'           THEN sessions ELSE 0 END) AS direct,
        SUM(CASE WHEN channel_group='Organic Search'   THEN sessions ELSE 0 END) AS organic_search,
        SUM(CASE WHEN channel_group='SMS'              THEN sessions ELSE 0 END) AS sms,
        SUM(CASE WHEN channel_group='Cross-network'    THEN sessions ELSE 0 END) AS cross_network,
        SUM(CASE WHEN channel_group='Referral'         THEN sessions ELSE 0 END) AS referral,
        SUM(CASE WHEN channel_group='Paid Shopping'    THEN sessions ELSE 0 END) AS paid_shopping,
        SUM(CASE WHEN channel_group='Organic Shopping' THEN sessions ELSE 0 END) AS organic_shopping,
        SUM(CASE WHEN channel_group='Organic Video'    THEN sessions ELSE 0 END) AS organic_video,
        SUM(CASE WHEN channel_group='Paid Other'       THEN sessions ELSE 0 END) AS paid_other,
        SUM(CASE WHEN channel_group='Unassigned'       THEN sessions ELSE 0 END) AS unassigned
    FROM (SELECT date, regexp_extract(landing_page,'(/products/[^/?#]+)',1) AS ga_url,
                 channel_group, sessions
          FROM analytics_catalog.analytics_platform.ga4_silver_traffic)
    WHERE ga_url <> '' GROUP BY date, ga_url
)
SELECT
    s.date,
    s.ga_url AS page,
    COALESCE(gp.event_count, 0)  AS event_count,
    COALESCE(gp.add_to_carts, 0) AS add_to_cart,
    s.unique_orders,
    s.units_sold AS unique_sold,
    s.net_sales,
    s.category, s.gender, s.descr,
    COALESCE(gt.email,0) AS email, COALESCE(gt.paid_search,0) AS paid_search,
    COALESCE(gt.paid_social,0) AS paid_social, COALESCE(gt.affiliates,0) AS affiliates,
    COALESCE(gt.organic_social,0) AS organic_social, COALESCE(gt.direct,0) AS direct,
    COALESCE(gt.organic_search,0) AS organic_search, COALESCE(gt.sms,0) AS sms,
    COALESCE(gt.cross_network,0) AS cross_network, COALESCE(gt.referral,0) AS referral,
    COALESCE(gt.paid_shopping,0) AS paid_shopping, COALESCE(gt.organic_shopping,0) AS organic_shopping,
    COALESCE(gt.organic_video,0) AS organic_video, COALESCE(gt.paid_other,0) AS paid_other,
    COALESCE(gt.unassigned,0) AS unassigned
FROM shopify_agg s
LEFT JOIN ga4_page          gp ON s.date = gp.date AND s.ga_url = gp.ga_url
LEFT JOIN ga4_traffic_pivot gt ON s.date = gt.date AND s.ga_url = gt.ga_url;