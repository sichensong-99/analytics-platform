# Data Contract: Triple Whale Attribution

**Status**: Draft (upstream not ready)
**Version**: v1.0
**Owner**: data-team
**Last Updated**: 2026-04-28
**Producers**: Databricks team (Triple Whale ingestion pipeline)
**Consumers**: Metrics Service, Internal Analytics Portal

---

## 1. Source

- **System**: Triple Whale API
- **Ingestion Method**: Daily batch via Databricks
- **Refresh Frequency**: Daily at 03:00 UTC
- **SLA**: Data freshness ≤ 24 hours

---

## 2. Grain

One row = one ad attribution event (order-level, attributed to a channel)

---

## 3. Schema

| Column | Type | Nullable | Description | Example |
|---|---|---|---|---|
| attribution_id | STRING | NO | Unique attribution event ID | "tw_8821" |
| order_id | STRING | NO | Linked Shopify order ID | "5821394821" |
| channel | STRING | NO | Ad channel: facebook / google / tiktok / organic | "facebook" |
| campaign_id | STRING | YES | Ad campaign ID | "camp_1023" |
| ad_spend | DECIMAL(10,2) | NO | Ad spend allocated to this order | 12.50 |
| attributed_revenue | DECIMAL(10,2) | NO | Revenue attributed to this channel | 129.99 |
| attribution_model | STRING | NO | last_click / first_click / linear | "last_click" |
| event_date | DATE | NO | Attribution event date (UTC) | 2026-04-28 |

---

## 4. Quality Expectations

- `attribution_id` is unique, not null
- `order_id` must exist in `dwd.fact_orders`
- `ad_spend` >= 0
- `attributed_revenue` >= 0
- `channel` in {facebook, google, tiktok, organic, email, other}

---

## 5. Layer Mapping

| Layer | Table | Purpose |
|---|---|---|
| ODS | `ods.triplewhale_attribution_raw` | Raw attribution data |
| DWD | `dwd.fact_attribution` | Cleaned attribution fact table |
| DWS | `dws.channel_performance` | Channel-level aggregated performance |

---

## 6. Downstream Usage

- Metric: `roas_by_channel` (DWS)
- Metric: `cac_by_channel` (DWS)
- Metric: `ad_spend_by_day` (DWS)
- Dashboard: Ad Attribution

---

## 7. Change Log

| Version | Date | Change | Author |
|---|---|---|---|
| v1.0 | 2026-04-28 | Initial draft | You |