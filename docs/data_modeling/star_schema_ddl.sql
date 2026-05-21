-- ============================================================================
-- File:        star_schema_ddl.sql
-- Project:     Internal Analytics Platform (PBI replacement, 32Degrees)
-- Layer:       DWD (Kimball dimensional model)
-- Schema:      mvdevdatabricks.analytics_platform_32degrees
-- Author:      Sia Song
-- Created:     2026-05-18
-- Version:     1.1 (Slice 1)
-- Slice:       1 of N — supports Style-channel (quantity) PBI page migration
-- ============================================================================
--
-- Changelog
-- ----------------------------------------------------------------------------
-- v1.1 (2026-05-18)
--   - dim_channel: dropped `is_web_attributed` and `is_operational` flags
--     (Excluded/Non-attributed now display as-is, matching TW UI)
--   - dim_channel: renamed `ga4_channel_name` to `legacy_channel_group` for
--     future-proof naming (not tied to GA4 specifically)
--   - All other tables unchanged
--
-- v1.0 (2026-05-18)
--   - Initial schema design (slice 1)
--
-- Purpose
-- ----------------------------------------------------------------------------
-- DDL for the first vertical slice of the new analytics platform's Kimball
-- dimensional model. Supports the Style-channel (quantity) PBI page
-- migration (see docs/existing_data_inventory.md §5.1) and provides
-- foundation for subsequent slices (revenue, refund analysis, etc.).
--
-- Star schema
-- ----------------------------------------------------------------------------
--   dim_date         ─┐
--   dim_product      ─┼─→ fact_orders_line  (grain: 1 row per order_line)
--   dim_channel      ─┘
--
-- Key design decisions
-- ----------------------------------------------------------------------------
--   1. Date taxonomy: ISO 8601 only (Monday-based weeks). US-week dropped
--      after stakeholder confirmation that legacy PBI reconciliation is
--      not required.
--   2. SCD strategy: SCD1 for v1 (YAGNI — upgrade to SCD2 deferred until
--      actual business case emerges).
--   3. Measure scope: quantity (slice 1 need) + line_total + line_discount
--      (slice 2 forward-looking, avoids full-table ETL rerun).
--   4. Data window: slice 1 ETL targets 2025-07-01 onwards (overlap with
--      Triple Whale attribution coverage). Schema itself is temporally
--      unbounded for future backfill of pre-TW Shopify history.
--   5. Channel display strategy: dim_channel carries BOTH channel_source
--      (raw TW value, for operations team) AND legacy_channel_group
--      (GA4-style grouping, for executive familiarity). Same dimension
--      serves two user groups without forcing either to learn the other's
--      vocabulary.
--
-- Execution
-- ----------------------------------------------------------------------------
--   1. Prerequisites:
--      - schema mvdevdatabricks.analytics_platform_32degrees exists
--      - executing user has CREATE TABLE / MODIFY privileges
--      (see Databricks access request email dated 2026-05-18)
--   2. Run order: dim tables first (no FK dependencies between them),
--      fact table last.
--   3. All tables are CREATE TABLE IF NOT EXISTS — safe to re-run.
--
-- ============================================================================

USE CATALOG mvdevdatabricks;
USE SCHEMA analytics_platform_32degrees;

-- ============================================================================
-- dim_channel — Marketing channel dimension
-- ----------------------------------------------------------------------------
-- Source      : triple_whale.attribution_order_click.source (seeded, not derived)
-- Grain       : one row per distinct Triple Whale channel source
-- Load        : version-controlled seed (see notebook 02_seed_dim_channel)
-- SCD         : SCD1 (overwrite) — see Decision 12
--
-- Changelog
--   v1.0  Initial 4-table star schema.
--   v1.1  Dropped is_web_attributed / is_operational; renamed ga4_channel_name
--         -> legacy_channel_group. (Decision 16)
--   v2.0  (2026-05-21) Full rebuild:
--           - Seed values switched from GUESSED to real attribution_order_click
--             .source values (guessed values were the root cause of the
--             notebook 04 channel DQ FAIL — 44.5% channel_key=0).
--           - Renamed legacy_channel_group -> channel_group, repositioned from
--             "GA4-legacy compatibility column" to a Kimball roll-up hierarchy
--             level. (Decision 21, supersedes Decision 15)
--           - Added is_meta_category to explicitly flag TW operational
--             meta-categories (Non-attributed / Excluded). (Decision 14)
--           - channel_key = 0 is permanently reserved for the explicit
--             'Unknown' catch-all member.
--
-- Design notes
--   - channel_source  : Triple Whale raw value, matches TW portal 1:1. This is
--                       the default display value in the frontend portal so
--                       operators see the same labels as in the TW portal.
--   - channel_group   : roll-up hierarchy level for executive aggregation
--                       (Paid Search / Paid Social / Email / Organic / ...).
--                       NOT a GA4-compatibility field — it is the dimension's
--                       drill hierarchy (channel_source -> channel_group).
--   - is_paid         : TRUE only for paid advertising platforms carrying media
--                       ad_spend (the paid-media ROAS denominator). Affiliate
--                       and influencer are FALSE — commission-based cost, not
--                       media spend. Forward-looking for Slice 4 ROAS.
-- ============================================================================
CREATE TABLE IF NOT EXISTS dim_channel (
  channel_key      INT       COMMENT 'Surrogate key. 0 = Unknown catch-all member.',
  channel_source   STRING    COMMENT 'Triple Whale raw source value — matches TW portal exactly. Default frontend display value.',
  channel_group    STRING    COMMENT 'Roll-up hierarchy level for executive-level aggregation (Paid Search / Paid Social / Email / ...).',
  is_paid          BOOLEAN   COMMENT 'TRUE = paid advertising platform with media ad_spend (paid-media ROAS denominator).',
  is_meta_category BOOLEAN   COMMENT 'TRUE = TW operational meta-category (Non-attributed / Excluded), not a real marketing channel.',
  _seeded_at       TIMESTAMP COMMENT 'Seed load timestamp.'
)
USING DELTA
COMMENT 'Slice 1 channel dimension. Seeded from triple_whale.attribution_order_click.source. See notebook 02_seed_dim_channel.';


-- ============================================================================
-- 2. DIM_CHANNEL — Channel dimension from Triple Whale source
-- ----------------------------------------------------------------------------
-- 15 known TW source values + 1 unknown placeholder (channel_key = -1).
-- SCD1: monthly refresh from TW source, overwrite semantics.
--
-- Dual-display design:
--   - channel_source: raw TW value (e.g. 'google-ads', 'Excluded')
--     for operations team consistency with TW UI
--   - legacy_channel_group: GA4-style grouping (e.g. 'Paid Search')
--     for executive familiarity with legacy PBI report taxonomy
-- ============================================================================
CREATE TABLE IF NOT EXISTS dim_channel (
  channel_key             BIGINT    NOT NULL  COMMENT 'Surrogate key, -1 = unknown',
  channel_source          STRING    NOT NULL  COMMENT 'Raw value from TW.source',

  channel_name            STRING    NOT NULL  COMMENT 'Display name (currently equals channel_source for TW consistency)',
  legacy_channel_group    STRING              COMMENT 'GA4-style grouping for executive PBI familiarity (Paid Search/Paid Social/Affiliates/Direct/Organic Social/Email-SMS/Other)',
  channel_platform        STRING              COMMENT 'Underlying platform (Google/Meta/Microsoft/Pinterest/etc), NULL if N/A',

  is_paid                 BOOLEAN   NOT NULL  COMMENT 'TRUE for *-ads channels (slice 4+ ROAS metric)',
  is_active               BOOLEAN   NOT NULL  COMMENT 'Default UI hides FALSE channels (long-tail soft-deactivation)',

  created_at              TIMESTAMP NOT NULL,
  updated_at              TIMESTAMP NOT NULL
)
USING DELTA
COMMENT 'Channel dimension with dual-display taxonomy, SCD1.'
TBLPROPERTIES ('delta.autoOptimize.optimizeWrite' = 'true');


-- ============================================================================
-- 3. DIM_PRODUCT — Product dimension from ERS master data
-- ----------------------------------------------------------------------------
-- Sourced from monthly ERS CSV upload to Unity Catalog Volume.
-- SCD1: monthly overwrite. unique_identifier (SKU) is natural key.
-- ============================================================================
CREATE TABLE IF NOT EXISTS dim_product (
  product_key             BIGINT    NOT NULL  COMMENT 'Surrogate key, -1 = unknown',

  unique_identifier       STRING    NOT NULL  COMMENT 'SKU, ERS natural key',
  vend_id                 STRING              COMMENT 'Style code',
  master_style            STRING              COMMENT 'Higher-level aggregation',

  item_description        STRING              COMMENT 'Product name',
  product_group           STRING              COMMENT 'Prefixed: group is SQL reserved word',
  season                  STRING,
  gender                  STRING,
  product_class           STRING              COMMENT 'Prefixed: class is SQL reserved word',
  product_size            STRING              COMMENT 'Prefixed: size is SQL reserved word',

  list_price              DECIMAL(10, 2),
  unit_cost               DECIMAL(10, 2)      COMMENT 'For future margin analysis',

  matched_via             STRING              COMMENT 'sku / item_description / unmatched',

  created_at              TIMESTAMP NOT NULL,
  updated_at              TIMESTAMP NOT NULL,
  source_file             STRING              COMMENT 'Source ERS upload filename'
)
USING DELTA
COMMENT 'Product dimension from ERS master, SCD1.'
TBLPROPERTIES ('delta.autoOptimize.optimizeWrite' = 'true');


-- ============================================================================
-- 4. FACT_ORDERS_LINE — Order line fact table
-- ----------------------------------------------------------------------------
-- Grain: 1 row per Shopify order_line (with TW attribution overlaid).
-- Partitioned by date_key for query pruning.
-- ============================================================================
CREATE TABLE IF NOT EXISTS fact_orders_line (
  -- Surrogate FKs to dimension tables
  date_key                INT       NOT NULL,
  product_key             BIGINT    NOT NULL,
  channel_key             BIGINT    NOT NULL,

  -- Degenerate dimensions (business keys for traceability)
  order_id                BIGINT    NOT NULL  COMMENT 'Shopify order.id',
  order_name              STRING    NOT NULL  COMMENT 'Shopify order.name (e.g. #12345)',
  order_line_id           BIGINT    NOT NULL  COMMENT 'Shopify order_line.id, grain key',
  customer_id             BIGINT              COMMENT 'NULL for guest checkout',
  sku                     STRING              COMMENT 'Raw SKU from order_line for traceability',

  -- Time facts
  order_created_at        TIMESTAMP NOT NULL,
  order_processed_at      TIMESTAMP,

  -- Measures (additive)
  quantity                INT       NOT NULL  COMMENT 'Units sold in this line',
  line_price              DECIMAL(10, 2)      COMMENT 'Unit price before discount',
  line_total              DECIMAL(10, 2)      COMMENT 'Final line revenue (slice 2 measure)',
  line_discount           DECIMAL(10, 2)      COMMENT 'Discount applied to this line',

  -- Status flags (v1 default FALSE, populated by future slices)
  is_refunded             BOOLEAN   NOT NULL  COMMENT 'Slice 3 populates this',
  is_replaced             BOOLEAN   NOT NULL  COMMENT 'Slice 3 populates this',
  is_cancelled            BOOLEAN   NOT NULL,

  -- TW attribution metadata
  tw_attribution_model    STRING              COMMENT 'linear (v1 default)',
  tw_attribution_position INT                 COMMENT 'For future first-touch/last-touch attribution',

  -- ETL audit
  etl_job_id              STRING,
  etl_loaded_at           TIMESTAMP NOT NULL,
  source_shopify_synced_at TIMESTAMP,
  source_tw_synced_at     TIMESTAMP
)
USING DELTA
PARTITIONED BY (date_key)
COMMENT 'Order line fact. Grain: 1 row per Shopify order_line with TW attribution.'
TBLPROPERTIES ('delta.autoOptimize.optimizeWrite' = 'true');
