CREATE TABLE IF NOT EXISTS etl_watermark (
    pipeline_name VARCHAR(64) PRIMARY KEY,
    last_processed_order_date DATE,
    last_run_at DATETIME,
    last_run_status VARCHAR(32)
);

INSERT INTO etl_watermark (
    pipeline_name,
    last_processed_order_date,
    last_run_at,
    last_run_status
)
SELECT
    'classicmodels_sales',
    MAX(orderDate),
    NULL,
    'NEVER_RUN'
FROM orders
ON DUPLICATE KEY UPDATE
    last_processed_order_date =
        COALESCE(last_processed_order_date, VALUES(last_processed_order_date)),
    last_run_status =
        COALESCE(last_run_status, VALUES(last_run_status));