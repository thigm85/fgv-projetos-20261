from __future__ import annotations
from decimal import Decimal

# RDS / extract (MySQL) 
SOURCE_TABLES: tuple[str, ...] = (
    "customers",
    "orders",
    "orderdetails",
    "products",
    "offices",
)

# Star schema
STAR_SCHEMA_OUTPUT_TABLES: tuple[str, ...] = (
    "fact_orders",
    "dim_customers",
    "dim_products",
    "dim_dates",
    "dim_countries",
)

FACT_TABLE_NAME: str = "fact_orders"

FACT_COLUMNS: frozenset[str] = frozenset(
    {
        "order_id",
        "customer_id",
        "product_id",
        "order_date_key",
        "country_key",
        "quantity_ordered",
        "price_each",
        "sales_amount",
    }
)

STAR_REFERENTIAL_KEYS: tuple[tuple[str, str, str], ...] = (
    ("dim_customers", "customer_id", "customer_id"),
    ("dim_products", "product_id", "product_id"),
    ("dim_dates", "order_date_key", "date_key"),
    ("dim_countries", "country_key", "country_key"),
)

# Validation: sales_amount ~ quantity_ordered * price_each
SALES_AMOUNT_MAX_DELTA_GLUE: float = 0.01
SALES_AMOUNT_MAX_DELTA_VALIDATE: Decimal = Decimal("0.02")

# S3 paths
S3_DATA_PREFIX: str = "warehouse/star"
S3_SCRIPTS_PREFIX: str = "glue/assets"
