-- ============================================================================
-- File:        star_schema_ddl.sql
-- Project:     Internal Analytics Platform (PBI replacement, 32Degrees)
-- Layer:       DWD (Kimball dimensional model)
-- Schema:      mvdevdatabricks.analytics_platform_32degrees
-- Author:      Sia Song
-- Created:     2026-05-18
-- Version:     1.0 (Slice 1)
-- Slice:       1 of N — supports Style-channel (quantity) PBI page migration
-- ============================================================================
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
--   5. Channel meta-categories: Non-attributed (non-web channels like Shop
--      app) and Excluded (operational orders like exchanges/drafts) modeled
--      explicitly with is_web_attributed + is_operational flags rather than
--      dropped, per consultation with TW data owner.
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
-- 1. DIM_DATE — Conformed date dimension (ISO 8601)
-- ----------------------------------------------------------------------------
-- Static reference table. Pre-generated for 2023-01-01 to 2030-12-31.
-- ============================================================================
CREATE TABLE IF NOT EXISTS dim_date (
  date_key                INT       NOT NULL  COMMENT 'YYYYMMDD format, PK',
  date_value              DATE      NOT NULL  COMMENT 'Actual calendar date',

  -- Basic components
  year                    INT       NOT NULL,
  quarter                 INT       NOT NULL  COMMENT '1-4',
  month                   INT       NOT NULL,
  month_name              STRING    NOT NULL  COMMENT 'January, February, ...',
  day_of_month            INT       NOT NULL,
  day_of_year             INT       NOT NULL,

  -- ISO 8601 (Monday-based weeks)
  iso_year                INT       NOT NULL,
  iso_week                INT       NOT NULL  COMMENT '1-53, Monday-based',
  iso_day_of_week         INT       NOT NULL  COMMENT '1=Mon, ..., 7=Sun',
  iso_year_week           STRING    NOT NULL  COMMENT 'YYYY-W## display format',
  iso_week_start_date     DATE      NOT NULL  COMMENT 'Monday of this week',
  iso_week_end_date       DATE      NOT NULL  COMMENT 'Sunday of this week',

  -- Period bookends
  month_start_date        DATE      NOT NULL,
  month_end_date          DATE      NOT NULL,
  quarter_start_date      DATE      NOT NULL,
  quarter_end_date        DATE      NOT NULL,

  -- Business flags
  day_name                STRING    NOT NULL  COMMENT 'Monday, Tuesday, ...',
  is_weekend              BOOLEAN   NOT NULL,

  -- Audit
  created_at              TIMESTAMP NOT NULL
)
USING DELTA
COMMENT 'Conformed date dimension, ISO 8601 standard.'
TBLPROPERTIES ('delta.autoOptimize.optimizeWrite' = 'true');


-- ============================================================================
-- 2. DIM_CHANNEL — Channel dimension from Triple Whale source
-- ----------------------------------------------------------------------------
-- 15 known TW source values + 1 unknown placeholder (channel_key = -1).
-- SCD1: monthly refresh from TW source, overwrite semantics.
-- ============================================================================
CREATE TABLE IF NOT EXISTS dim_channel (
  channel_key             BIGINT    NOT NULL  COMMENT 'Surrogate key, -1 = unknown',
  channel_source          STRING    NOT NULL  COMMENT 'Raw value from TW.source',

  channel_name            STRING    NOT NULL  COMMENT 'Display name (e.g. Google Ads)',
  channel_category        STRING    NOT NULL  COMMENT 'Paid Search/Paid Social/Affiliate/Organic/Direct/Meta-Category/Other',
  channel_platform        STRING              COMMENT 'Google/Meta/Microsoft/etc, NULL if N/A',

  is_web_attributed       BOOLEAN   NOT NULL  COMMENT 'FALSE for Non-attributed (non-web) and Excluded',
  is_operational          BOOLEAN   NOT NULL  COMMENT 'TRUE for Excluded (exchanges, drafts)',
  is_paid                 BOOLEAN   NOT NULL  COMMENT 'TRUE for *-ads channels',
  is_active               BOOLEAN   NOT NULL  COMMENT 'Default UI hides FALSE channels',

  ga4_channel_name        STRING              COMMENT 'GA4 grouping for dual-taxonomy historical view',

  created_at              TIMESTAMP NOT NULL,
  updated_at              TIMESTAMP NOT NULL
)
USING DELTA
COMMENT 'Channel dimension, SCD1.'
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
