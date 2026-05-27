-- ============================================================================
-- File:        star_schema_ddl.sql
-- Project:     Internal Analytics Platform (PBI replacement, 32Degrees)
-- Layer:       DWD (Kimball dimensional model)
-- Schema:      mvdevdatabricks.analytics_platform_32degrees
-- Author:      Sia Song
-- Version:     2.0 (Slice 1, Decision 22 v3)
-- ============================================================================
--
-- Changelog
-- ----------------------------------------------------------------------------
-- v2.0 (2026-05-27)
--   - Removed duplicate dim_channel block (v1.1 legacy retained, v2.0 wins).
--   - dim_channel v2.0 — real TW seed values + channel_group roll-up
--     hierarchy + is_meta_category. (Decisions 14, 16, 21)
--   - dim_product synced to actual notebook 03 output (column names + types).
--   - dim_date synced to actual notebook 01 output.
--   - fact_orders_line rewritten to Decision 22 v3:
--       * added refunded_quantity (line-level net deduction, all restock types)
--       * is_sales_attributable = NOT(is_exc_order OR is_replacement_order)
--       * dropped is_refunded, is_refund_order, is_replaced, is_cancelled
--       * partition switched to (iso_year, iso_week) — matches notebook 04
--       * date_key BIGINT to match dim_date.date_key
--
-- v1.1 (2026-05-18)
--   - dim_channel: dropped is_web_attributed / is_operational; renamed
--     ga4_channel_name -> legacy_channel_group.
--
-- v1.0 (2026-05-18)
--   - Initial schema design (Slice 1).
--
-- Purpose
-- ----------------------------------------------------------------------------
-- Slice 1 Kimball star schema. Supports Style-channel (quantity) PBI page
-- migration. Foundation for subsequent slices (revenue, refund analysis, ROAS).
--
-- Star schema
-- ----------------------------------------------------------------------------
--   dim_date    ─┐
--   dim_product ─┼─→ fact_orders_line  (grain: 1 row per Shopify order_line)
--   dim_channel ─┘
--
-- Key decisions
-- ----------------------------------------------------------------------------
--   * ISO 8601 only (Decision 11).
--   * SCD1 for v1 (Decision 12 — YAGNI; SCD2 deferred until justified).
--   * Schema temporally unbounded; ETL window starts 2025-07-01 (Decision 13).
--   * channel_source = TW raw display value; channel_group = roll-up hierarchy
--     (Decision 21, supersedes Decision 15 v1).
--   * is_paid forward-looking flag retained (Decision 16).
--   * is_meta_category flags TW operational meta-categories (Decision 14).
--   * Sales exclusion materialized as is_sales_attributable (Decision 22 v3).
--     Refund handled as line-level net deduction via refunded_quantity, NOT
--     order-level exclusion — order-level refund exclusion was disproven by
--     Day-5 reconciliation (residual worsened 1.97% -> 6.57%).
-- ============================================================================

USE CATALOG mvdevdatabricks;
USE SCHEMA analytics_platform_32degrees;


-- ============================================================================
-- DIM_DATE — Calendar dimension
-- ----------------------------------------------------------------------------
-- Source : Python-generated via scripts/generate_dim_date.py (Decision uses
--          datetime.isocalendar() to avoid SQL-dialect ISO inconsistencies).
-- Grain  : one row per calendar day.
-- Range  : 2023-01-01 .. 2030-12-31 (2,922 rows).
-- SCD    : N/A (static reference).
-- ============================================================================
CREATE TABLE IF NOT EXISTS dim_date (
  date_key         BIGINT  NOT NULL  COMMENT 'PK, yyyyMMdd integer encoding.',
  date_actual      STRING  NOT NULL  COMMENT 'ISO date string YYYY-MM-DD.',
  iso_year         BIGINT  NOT NULL  COMMENT 'ISO 8601 year (week-Monday based).',
  iso_week         BIGINT  NOT NULL  COMMENT 'ISO 8601 week number 1-53.',
  iso_day_of_week  BIGINT  NOT NULL  COMMENT 'ISO day-of-week, Mon=1 .. Sun=7.',
  cal_year         BIGINT  NOT NULL  COMMENT 'Calendar Gregorian year.',
  cal_month        BIGINT  NOT NULL  COMMENT 'Calendar month 1-12.',
  cal_day          BIGINT  NOT NULL  COMMENT 'Calendar day-of-month 1-31.',
  cal_quarter      BIGINT  NOT NULL  COMMENT 'Calendar quarter 1-4.',
  month_name       STRING  NOT NULL  COMMENT 'English month name.',
  day_name         STRING  NOT NULL  COMMENT 'English day name.',
  is_weekend       BOOLEAN NOT NULL  COMMENT 'TRUE for Saturday + Sunday.'
)
USING DELTA
COMMENT 'ISO 8601 calendar dimension. See notebook 01_build_dim_date.';


-- ============================================================================
-- DIM_CHANNEL — Marketing channel dimension
-- ----------------------------------------------------------------------------
-- Source : Seeded from triple_whale.attribution_order_click.source.
-- Grain  : one row per distinct TW channel source value.
-- SCD    : SCD1 (overwrite seed). See notebook 02_seed_dim_channel.
-- Notes  : channel_key = 0 is permanently reserved for the Unknown catch-all.
-- ============================================================================
CREATE TABLE IF NOT EXISTS dim_channel (
  channel_key       INT                COMMENT 'Surrogate key. 0 = Unknown catch-all.',
  channel_source    STRING             COMMENT 'TW raw source — matches TW portal 1:1. Default frontend display value.',
  channel_group     STRING             COMMENT 'Roll-up hierarchy level (Paid Search / Paid Social / Email / Organic / ...).',
  is_paid           BOOLEAN            COMMENT 'TRUE = paid advertising platform carrying media ad_spend (ROAS denominator).',
  is_meta_category  BOOLEAN            COMMENT 'TRUE = TW operational meta-category (Non-attributed / Excluded), not a real marketing channel.',
  _seeded_at        TIMESTAMP          COMMENT 'Seed load timestamp.'
)
USING DELTA
COMMENT 'Slice 1 channel dimension. Seeded from triple_whale.attribution_order_click.source.';


-- ============================================================================
-- DIM_PRODUCT — Product dimension from ERS master data
-- ----------------------------------------------------------------------------
-- Source : ERS monthly CSV via shared raw zone (Decision 20).
-- Grain  : one row per SKU.
-- SCD    : SCD1 (monthly overwrite). See notebook 03_build_dim_product.
-- Notes  : Schema-evolution-tolerant ingest auto-detects legacy vs current
--          ERS format and normalizes to the columns below (Decision 19).
-- ============================================================================
CREATE TABLE IF NOT EXISTS dim_product (
  product_key           INT                COMMENT 'Surrogate key.',
  sku                   STRING             COMMENT 'ERS natural key (unique_identifier in legacy / SKU in current format).',
  vend_id               STRING             COMMENT 'Style code (Vend_ID in legacy / Style# in current format).',
  item_description      STRING             COMMENT 'Product name.',
  season                STRING             COMMENT 'Product season; missing values normalized to "Others".',
  group_name            STRING             COMMENT 'ERS group (prefixed: `group` is a SQL reserved word).',
  gender                STRING,
  class_name            STRING             COMMENT 'ERS class (prefixed: `class` is a SQL reserved word).',
  master_style          STRING             COMMENT 'Higher-level style aggregation (current ERS format only).',
  cost                  DECIMAL(10,2)      COMMENT 'Product cost for future margin analysis.',
  retail                DECIMAL(10,2)      COMMENT 'Retail price.',
  is_complete           BOOLEAN            COMMENT 'TRUE if all critical fields populated post-normalization.',
  _ers_schema_version   STRING             COMMENT 'Detected ERS schema version: legacy / current.',
  _ingested_at          TIMESTAMP          COMMENT 'ETL load timestamp.'
)
USING DELTA
COMMENT 'Product dimension from ERS master, SCD1, dual-schema tolerant.';


-- ============================================================================
-- FACT_ORDERS_LINE — Order line sales fact (Slice 1)
-- ----------------------------------------------------------------------------
-- Grain  : 1 row per Shopify order_line, with TW last-touch attribution.
-- Refund : line-level net deduction via refunded_quantity. NOT an order-level
--          exclusion (disproven by Day-5 reconciliation). Decision 22 v3.
-- ============================================================================
CREATE TABLE IF NOT EXISTS fact_orders_line (
  -- Surrogate FKs to conformed dimensions
  channel_key            INT                 COMMENT 'FK -> dim_channel. 0 = Unknown catch-all.',
  product_key            INT                 COMMENT 'FK -> dim_product. NULL = order_line.sku unmatched to ERS.',
  date_key               BIGINT    NOT NULL  COMMENT 'FK -> dim_date (yyyyMMdd), DST-aware America/New_York.',

  -- Degenerate dimensions
  shopify_order_id       STRING    NOT NULL  COMMENT 'Shopify order.id (string).',
  shopify_order_name     STRING              COMMENT 'Shopify order.name, e.g. #12345 / ...EXC...',
  tw_order_id            STRING              COMMENT 'TW _triple_whale_order_id. NULL = no TW attribution.',
  shopify_line_id        STRING    NOT NULL  COMMENT 'Shopify order_line.id — grain key.',
  sku_raw                STRING              COMMENT 'Raw SKU from order_line for traceability.',

  -- Additive measures
  quantity               INT       NOT NULL  COMMENT 'Gross units on this line.',
  refunded_quantity      INT       NOT NULL  COMMENT 'Units refunded on this line — SUM(order_line_refund.quantity) across ALL restock_type values (return / no_restock / cancel / legacy_restock). 0 if none. Net = quantity - refunded_quantity.',
  pre_tax_price          DECIMAL(10,2)       COMMENT 'Unit price before tax/discount (order_line.price).',

  -- TW attribution metadata (forward-looking for Slice 4 ROAS)
  tw_channel_source      STRING              COMMENT 'Raw TW source value.',
  channel_source_norm    STRING              COMMENT 'Normalized TW source used for dim_channel join.',
  tw_touch_ts            TIMESTAMP           COMMENT 'TW click_date of the last-touch row.',
  attribution_model      STRING              COMMENT 'TW attribution_model.',
  position               INT                 COMMENT 'TW touch position (last-touch dedup key).',
  campaign_id            STRING,
  adset_id               STRING,
  ad_id                  STRING,

  -- Order status + materialized business-rule flags (Decision 22 v3)
  financial_status       STRING              COMMENT 'Shopify order.financial_status (raw, informational).',
  is_exc_order           BOOLEAN   NOT NULL  COMMENT 'Whole-order exclusion: order.name contains EXC.',
  is_replacement_order   BOOLEAN   NOT NULL  COMMENT 'Whole-order exclusion: replacement order_metafield (replace_refund = ''["Replace"]''). FALSE until Fivetran syncs order_metafield table — graceful degradation.',
  is_sales_attributable  BOOLEAN   NOT NULL  COMMENT 'NOT(is_exc_order OR is_replacement_order). Refunds are NOT excluded here — netted at line grain via refunded_quantity.',

  -- ISO 8601 date attributes (also partition columns)
  iso_year               BIGINT    NOT NULL,
  iso_week               BIGINT    NOT NULL,

  -- Lineage
  _ingested_at           TIMESTAMP NOT NULL  COMMENT 'ETL load timestamp.'
)
USING DELTA
PARTITIONED BY (iso_year, iso_week)
COMMENT 'Slice 1 order-line sales fact. Grain: 1 row per Shopify order_line with TW last-touch attribution. Decision 22 v3 — refund as line-level net deduction.'
TBLPROPERTIES ('delta.autoOptimize.optimizeWrite' = 'true');

