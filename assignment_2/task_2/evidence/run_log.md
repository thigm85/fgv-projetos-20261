# Task 2 Run Log

Use this file to record the required execution evidence.

## Manual run 1

- `simulate_new_orders` command:
- Glue Job Run ID:
- Previous watermark:
- New watermark:
- Orders extracted:
- `fact_orders` rows added:
- S3 partitions touched:
- Athena validation query:
- Result:

## Manual run 2

- `simulate_new_orders` command:
- Glue Job Run ID:
- Previous watermark:
- New watermark:
- Orders extracted:
- `fact_orders` rows added:
- S3 partitions touched:
- Athena validation query:
- Result:

## EventBridge run

- EventBridge rule:
- Glue Workflow Run ID:
- Glue Job Run ID:
- Trigger timestamp UTC:
- Result:

## Notes

- Confirm that only orders with `orderDate` greater than the previous watermark were extracted.
- Confirm that `sales_amount = quantity_ordered * price_each` for the new rows.
- Confirm that Athena can query `fact_orders` with `order_year` and `order_month` filters.

## Automated run - 2026-06-12 02:22:41 UTC

- Glue Job: `tomas-classicmodels-task2-incremental-etl`
- Glue Job Run ID: `jr_e8b453b93cc837de7789c9dd0e8a1049dc29fac4f01cae22ea2d36f7925628cb`
- Glue Job State: `SUCCEEDED`
- S3 bucket: `tomas-classicmodels-task2-991815483166`
- Glue database: `tomas_classicmodels_task2_analytics`
- Previous watermark: `2005-05-31`
- Simulated orders: `[10426, 10427, 10428, 10429, 10430]`
- Simulated date range: `2005-06-01 to 2005-06-07`
- Simulated orderdetails rows: `7`
- Watermark after run: `{'last_processed_order_date': datetime.date(2005, 6, 7), 'last_run_status': 'SUCCEEDED'}`
- S3 fact object count under `analytics/fact_orders/`: `1`
- Glue Catalog partitions for `fact_orders`: `[['2005', '6']]`
