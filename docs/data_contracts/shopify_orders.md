# Data Contract: Shopify Orders

**Status**: Draft (upstream not ready)
**Version**: v1.0
**Owner**: data-team
**Last Updated**: 2026-04-28
**Producers**: Databricks team (Shopify ingestion pipeline)
**Consumers**: Metrics Service, Internal Analytics Portal

---

## 1. Source

- **System**: Shopify Admin API
- **Ingestion Method**: Daily batch (TBD: Fivetran / Airbyte / custom)
- **Refresh Frequency**: Daily at 02:00 UTC
- **SLA**: Data freshness ≤ 24 hours

---

## 2. Grain

One row = one Shopify order (order-level)

---

## 3. Schema

| Column | Type | Nullable | Description | Example |
|---|---|---|---|---|
| order_id | STRING | NO | Shopify order ID | "5821394821" |
| customer_id | STRING | YES | Customer ID, NULL for guest orders | "C8821" |
| order_date | DATE | NO | Order date (UTC) | 2026-04-28 |
| created_at | TIMESTAMP | NO | Order timestamp (UTC) | 2026-04-28 10:23:11 |
| total_price | DECIMAL(10,2) | NO | Total order amount | 129.99 |
| currency | STRING | NO | Currency code (ISO 4217) | "USD" |
| financial_status | STRING | NO | paid / refunded / pending / voided | "paid" |
| fulfillment_status | STRING | YES | Fulfillment status | "fulfilled" |
| line_items_count | INTEGER | NO | Number of line items | 3 |

---

## 4. Quality Expectations

- `order_id` is unique, not null
- `total_price` >= 0
- `order_date` between 2020-01-01 and today
- `financial_status` in {paid, refunded, pending, voided}
- Daily order count should not drop > 50% vs 7-day average (alert)

---

## 5. Layer Mapping

| Layer | Table | Purpose |
|---|---|---|
| ODS | `ods.shopify_orders_raw` | Raw data, all fields preserved |
| DWD | `dwd.fact_orders` | Cleaned order fact table |
| DWS | `dws.daily_revenue` | Daily aggregated revenue metrics |

---

## 6. Downstream Usage

- Metric: `revenue_by_day` (DWS)
- Metric: `aov_by_day` (DWS)
- Metric: `order_count_by_day` (DWS)
- Dashboard: Shopify Sales Overview

---

## 7. Change Log

| Version | Date | Change | Author |
|---|---|---|---|
| v1.0 | 2026-04-28 | Initial draft based on Shopify API spec | You |