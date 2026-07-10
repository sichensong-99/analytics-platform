-- ============================================================================
-- File:        dim_channel_seed.sql
-- Project:     Internal Analytics Platform (PBI replacement, the retailer)
-- Layer:       DWD (Kimball dimensional model)
-- Target:      analytics_catalog.analytics_platform.dim_channel
-- Author:      Sia Song
-- Created:     2026-05-18
-- Version:     1.0 (Slice 1)
-- ============================================================================
--
-- Purpose
-- ----------------------------------------------------------------------------
-- Seed data for the channel dimension. 16 rows = 1 unknown placeholder
-- (channel_key = -1) + 15 distinct source values observed in Triple Whale's
-- attribution_order_click table.
--
-- Why version-controlled seed SQL (not derived from source)?
-- ----------------------------------------------------------------------------
-- dim_channel is low-cardinality (~16 rows) and the categorization fields
-- (legacy_channel_group, is_paid, is_active) require business judgment that
-- cannot be derived from source data alone. Authoring these decisions as
-- reviewable, version-controlled SQL is the dimensional modeling best
-- practice for this pattern.
--
-- Design decisions
-- ----------------------------------------------------------------------------
--   1. channel_source preserved as-is from TW source values
--      - Rationale: Operations team uses TW UI daily; new platform shows the
--        same names to maintain cognitive consistency across tools.
--
--   2. legacy_channel_group added as a parallel display field
--      - Rationale: Executive (stakeholder) is accustomed to the legacy PBI
--        report's GA4-style channel groupings (Paid Search, Paid Social,
--        Affiliates, etc.). This field maps each TW source back to the
--        legacy grouping, enabling executive-friendly slicer defaults on
--        the new platform's front-end without forcing TW vocabulary on
--        end-users.
--      - This is a deliberate denormalization: same dimension carries two
--        display taxonomies (Conway's Law in data modeling).
--
--   3. is_paid retained as a forward-looking flag
--      - Rationale: Slice 4+ will introduce ROAS (Return on Ad Spend)
--        metrics. Pre-encoding which channels count as paid spend here
--        avoids ALTER TABLE + backfill when ROAS is introduced.
--
--   4. is_active flag for soft-deactivation of long-tail channels
--      - Rationale: 8 of 15 channels are long-tail (<1000 orders total).
--        Front-end slicer defaults to is_active = TRUE to avoid noise,
--        with a "show all channels" toggle to reveal long-tail.
--      - Rows are never deleted because fact rows reference them.
--
--   5. is_web_attributed and is_operational flags REMOVED in v1
--      - Rationale: User decided that Excluded and Non-attributed should
--        display as-is to match TW UI exactly. No default-hide behavior
--        needed, so these flags would be unused.
--
-- Execution
-- ----------------------------------------------------------------------------
--   1. Prerequisites: dim_channel table created (run star_schema_ddl.sql)
--   2. INSERT is idempotent via TRUNCATE-then-INSERT pattern: safe to re-run.
--   3. If new TW source values appear over time, append rows here and
--      re-run; ETL job logic in slice 1 (Day 3) will warn on unmapped
--      sources, prompting maintainer to extend this seed file.
--
-- ============================================================================

USE CATALOG analytics_catalog;
USE SCHEMA analytics_platform;


-- ============================================================================
-- Truncate to ensure idempotent re-run
-- ============================================================================
TRUNCATE TABLE dim_channel;


-- ============================================================================
-- Seed 16 rows
-- ============================================================================
INSERT INTO dim_channel (
    channel_key,
    channel_source,
    channel_name,
    legacy_channel_group,
    channel_platform,
    is_paid,
    is_active,
    created_at,
    updated_at
)
VALUES
    -- ────────────────────────────────────────────────────────────────────────
    -- Unknown placeholder (Kimball convention: -1 for unmapped values)
    -- Prevents NULL joins from fact to dim if unexpected source appears.
    -- ────────────────────────────────────────────────────────────────────────
    (-1, 'unknown',            'Unknown',             'Other',           NULL,            FALSE, TRUE,  CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP()),

    -- ────────────────────────────────────────────────────────────────────────
    -- Top 7 channels (99%+ of order volume, default-visible in front-end)
    -- ────────────────────────────────────────────────────────────────────────
    ( 1, 'google-ads',         'google-ads',          'Paid Search',     'Google',        TRUE,  TRUE,  CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP()),
    ( 2, 'facebook-ads',       'facebook-ads',        'Paid Social',     'Meta',          TRUE,  TRUE,  CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP()),
    ( 3, 'impact',             'impact',              'Affiliates',      'Impact',        TRUE,  TRUE,  CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP()),
    ( 4, 'bing',               'bing',                'Paid Search',     'Microsoft',     TRUE,  TRUE,  CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP()),
    ( 5, 'Excluded',           'Excluded',            'Other',           NULL,            FALSE, TRUE,  CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP()),
    ( 6, 'Direct',             'Direct',              'Direct',          NULL,            FALSE, TRUE,  CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP()),
    ( 7, 'Non-attributed',     'Non-attributed',      'Other',           NULL,            FALSE, TRUE,  CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP()),

    -- ────────────────────────────────────────────────────────────────────────
    -- Mid-volume channel (default-visible)
    -- ────────────────────────────────────────────────────────────────────────
    ( 8, 'organic_and_social', 'organic_and_social',  'Organic Social',  NULL,            FALSE, TRUE,  CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP()),
    ( 9, 'influencers',        'influencers',         'Affiliates',      NULL,            FALSE, TRUE,  CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP()),

    -- ────────────────────────────────────────────────────────────────────────
    -- Long-tail channels (<1000 orders, default-hidden via is_active = FALSE)
    -- ────────────────────────────────────────────────────────────────────────
    (10, 'pinterest-ads',      'pinterest-ads',       'Paid Social',     'Pinterest',     TRUE,  FALSE, CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP()),
    (11, 'snapchat-ads',       'snapchat-ads',        'Paid Social',     'Snapchat',      TRUE,  FALSE, CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP()),
    (12, 'tiktok-ads',         'tiktok-ads',          'Paid Social',     'TikTok',        TRUE,  FALSE, CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP()),
    (13, 'smsbump',            'smsbump',             'Email/SMS',       'SMSBump',       FALSE, FALSE, CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP()),
    (14, 'superfiliate',       'superfiliate',        'Affiliates',      'Superfiliate',  FALSE, FALSE, CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP()),
    (15, 'applovin',           'applovin',            'Paid Social',     'AppLovin',      TRUE,  FALSE, CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP())
;


-- ============================================================================
-- Verification queries (run after INSERT)
-- ============================================================================

-- Row count check (should return 16)
SELECT COUNT(*) AS total_rows FROM dim_channel;

-- Distribution by legacy_channel_group (stakeholder-facing taxonomy)
SELECT legacy_channel_group, COUNT(*) AS channel_count
FROM dim_channel
GROUP BY legacy_channel_group
ORDER BY channel_count DESC;

-- Paid channels (will be used for ROAS metric in slice 4+)
SELECT channel_source, channel_platform
FROM dim_channel
WHERE is_paid = TRUE
ORDER BY channel_key;

-- Active channels (default-visible in front-end slicer)
SELECT channel_source, legacy_channel_group
FROM dim_channel
WHERE is_active = TRUE
ORDER BY channel_key;
