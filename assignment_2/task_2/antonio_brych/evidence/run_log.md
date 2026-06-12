# Evidence — Incremental ETL Run Log

## Run 1 — Initial load

**Trigger:** Manual (`aws glue start-job-run`)
**Watermark in:** `2005-05-31` (last date in classicmodels orders)
**Watermark out:** *(set after simulated orders were added)*

### Glue job output (excerpt)
```
[ETL] watermark_in=2005-05-31
[ETL] new_orders_found=5
[ETL] fact_delta_rows=5
[ETL] Writing dimensions...
  dim written: dim_customers
  dim written: dim_products
  dim written: dim_dates
  dim written: dim_countries
[ETL] Merging fact partitions...
  fact partition written: order_year=2026/order_month=6
[ETL] Registering Glue Catalog partitions...
  Glue Catalog: 1 new partition(s) registered.
[ETL] Done. watermark_out=2026-06-07, fact_rows=5
```

## Run 2 — No new orders (idempotency check)

```
[ETL] watermark_in=2026-06-07
[ETL] new_orders_found=0
[ETL] No new orders above watermark — nothing to write.
```

Watermark status remains SUCCEEDED, no write operations performed.

## Athena validation

```sql
-- Row count
SELECT COUNT(*) FROM fact_orders;
-- Result: 5 (matches source orderdetails for simulated orders)

-- sales_amount integrity
SELECT COUNT(*) FROM fact_orders
WHERE ABS(sales_amount - CAST(quantity_ordered AS DOUBLE) * price_each) > 0.001;
-- Result: 0

-- Partition visibility
SELECT DISTINCT order_year, order_month FROM fact_orders;
-- Result: order_year=2026, order_month=6
```
