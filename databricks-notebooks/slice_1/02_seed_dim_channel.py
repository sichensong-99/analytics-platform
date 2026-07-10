# Databricks notebook — 02_seed_dim_channel
# Slice 1 · dim_channel
# v2.0 (2026-05-21):
#   - 全量重建:种子值改用 attribution_order_click.source 的真实值
#     (上一版用了 GUESSED 值 meta/klaviyo，是 notebook 04 channel DQ FAIL 的根因)
#   - 改列名 legacy_channel_group -> channel_group (定位为 Kimball roll-up 层级)
#   - channel_key = 0 固定保留给显式 'Unknown' 兜底成员

CATALOG = "analytics_catalog"
SCHEMA  = "analytics_platform"
TABLE   = f"{CATALOG}.{SCHEMA}.dim_channel"
print(f"Target: {TABLE}")

spark.sql(f"DROP TABLE IF EXISTS {TABLE}")

spark.sql(f"""
CREATE TABLE {TABLE} (
  channel_key      INT       COMMENT 'Surrogate key. 0 = Unknown catch-all member.',
  channel_source   STRING    COMMENT 'Triple Whale raw source value — matches TW portal exactly.',
  channel_group    STRING    COMMENT 'Roll-up hierarchy level for executive-level aggregation (Paid Search / Paid Social / Email / ...).',
  is_paid          BOOLEAN   COMMENT 'TRUE = paid advertising platform with media ad_spend (paid-media ROAS denominator).',
  is_meta_category BOOLEAN   COMMENT 'TRUE = TW operational meta-category (Non-attributed / Excluded), not a real marketing channel.',
  _seeded_at       TIMESTAMP COMMENT 'Seed load timestamp.'
)
USING DELTA
COMMENT 'Slice 1 channel dimension. Seeded from triple_whale.attribution_order_click.source. See notebook 02_seed_dim_channel.'
""")
print("dim_channel created.")

spark.sql(f"""
INSERT INTO {TABLE} VALUES
  (0,  'Unknown',            'Unknown',        false, false, current_timestamp()),
  (1,  'facebook-ads',       'Paid Social',    true,  false, current_timestamp()),
  (2,  'google-ads',         'Paid Search',    true,  false, current_timestamp()),
  (3,  'bing',               'Paid Search',    true,  false, current_timestamp()),
  (4,  'pinterest-ads',      'Paid Social',    true,  false, current_timestamp()),
  (5,  'impact',             'Affiliate',      false, false, current_timestamp()),
  (6,  'influencers',        'Influencer',     false, false, current_timestamp()),
  (7,  'Emarsys',            'Email',          false, false, current_timestamp()),
  (8,  'klaviyo',            'Email',          false, false, current_timestamp()),
  (9,  'Promotional',        'Email',          false, false, current_timestamp()),
  (10, 'Transactional',      'Email',          false, false, current_timestamp()),
  (11, 'Tactics',            'Email',          false, false, current_timestamp()),
  (12, 'attentive',          'SMS',            false, false, current_timestamp()),
  (13, 'organic_and_social', 'Organic',        false, false, current_timestamp()),
  (14, 'Direct',             'Direct',         false, false, current_timestamp()),
  (15, 'shop_app',           'Shop App',       false, false, current_timestamp()),
  (16, 'shop-website',       'Other',          false, false, current_timestamp()),
  (17, 'AMZN_US_ShopDirect', 'Marketplace',    false, false, current_timestamp()),
  (18, 'chatgpt.com',        'AI Search',      false, false, current_timestamp()),
  (19, 'perplexity',         'AI Search',      false, false, current_timestamp()),
  (20, 'copilot.com',        'AI Search',      false, false, current_timestamp()),
  (21, 'Non-attributed',     'Non-attributed', false, true,  current_timestamp()),
  (22, 'Excluded',           'Excluded',       false, true,  current_timestamp())
""")
print("dim_channel seeded.")

print("=== Row count ===")
display(spark.sql(f"SELECT COUNT(*) AS rows FROM {TABLE}"))

print("=== By channel_group (roll-up sanity check) ===")
display(spark.sql(f"""
  SELECT channel_group, COUNT(*) AS n_channels,
         CONCAT_WS(', ', COLLECT_LIST(channel_source)) AS channels
  FROM {TABLE} GROUP BY channel_group ORDER BY n_channels DESC
"""))

print("=== Paid channels ===")
display(spark.sql(f"SELECT channel_source FROM {TABLE} WHERE is_paid = true"))