
CREATE TABLE IF NOT EXISTS etl_watermark (
    pipeline_name             VARCHAR(64)  NOT NULL,
    last_processed_order_date DATE         NULL,
    last_run_at               DATETIME     NULL,
    last_run_status           VARCHAR(32)  NOT NULL DEFAULT 'NEVER_RUN',
    PRIMARY KEY (pipeline_name)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4;

INSERT INTO etl_watermark (
    pipeline_name,
    last_processed_order_date,
    last_run_at,
    last_run_status
)
SELECT
    'classicmodels_sales',
    (SELECT MAX(orderDate) FROM orders),
    NULL,
    'NEVER_RUN'
WHERE NOT EXISTS (
    SELECT 1 FROM etl_watermark WHERE pipeline_name = 'classicmodels_sales'
);

UPDATE etl_watermark
SET last_processed_order_date = (SELECT MAX(orderDate) FROM orders)
WHERE pipeline_name = 'classicmodels_sales'
  AND last_processed_order_date IS NULL;
