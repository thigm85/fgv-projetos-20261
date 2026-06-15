"""Shared constants for the incremental Glue ETL."""

PIPELINE_NAME_DEFAULT = "classicmodels_sales"
WATERMARK_TABLE_DEFAULT = "etl_watermark"


def watermark_date_str(value) -> str:
    if value is None:
        raise ValueError("last_processed_order_date is NULL; run Task 1 init_watermark first.")
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d")
    return str(value)[:10]

FACT_TABLE_NAME = "fact_orders"
FACT_KEYS = ["order_id", "product_id"]
SALES_TOLERANCE = 0.01

DIM_MERGE_CONFIG = {
    "dim_customers": (
        ["customer_id"],
        ["customer_id", "customer_name", "contact_name", "city", "country"],
    ),
    "dim_products": (
        ["product_id"],
        ["product_id", "product_name", "product_line", "product_vendor"],
    ),
    "dim_dates": (
        ["date_key"],
        ["date_key", "full_date", "year", "quarter", "month", "day"],
    ),
    "dim_countries": (
        ["country_key"],
        ["country_key", "country", "territory"],
    ),
}

FACT_DATA_COLUMNS = [
    "order_id",
    "customer_id",
    "product_id",
    "order_date_key",
    "country_key",
    "quantity_ordered",
    "price_each",
    "sales_amount",
]

STAR_REFERENTIAL_KEYS = [
    ("customer_id", "dim_customers", "customer_id"),
    ("product_id", "dim_products", "product_id"),
    ("order_date_key", "dim_dates", "date_key"),
    ("country_key", "dim_countries", "country_key"),
]
