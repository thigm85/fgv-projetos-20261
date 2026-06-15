"""Star-schema transforms for the incremental delta (dims + fact_orders)."""

from __future__ import annotations
from pyspark.sql import DataFrame
from pyspark.sql import functions as F


# ============================================================================
# Helpers
# ============================================================================

def _customer_ids(orders_delta: DataFrame) -> DataFrame:
    return (
        orders_delta
        .select(F.col("customerNumber").cast("int").alias("customer_id"))
        .distinct()
    )


def _product_ids(orderdetails_delta: DataFrame) -> DataFrame:
    return (
        orderdetails_delta
        .select(F.col("productCode").cast("string").alias("product_id"))
        .distinct()
    )


def _build_dim_customers(
    customers: DataFrame,
    customer_ids: DataFrame,
) -> DataFrame:
    return (
        customers
        .join(
            customer_ids,
            customers["customerNumber"] == customer_ids["customer_id"],
            "inner",
        )
        .select(
            F.col("customerNumber").cast("int").alias("customer_id"),
            F.col("customerName").cast("string").alias("customer_name"),
            F.concat_ws(
                " ",
                F.col("contactFirstName"),
                F.col("contactLastName"),
            ).cast("string").alias("contact_name"),
            F.col("city").cast("string").alias("city"),
            F.col("country").cast("string").alias("country"),
        )
        .dropDuplicates(["customer_id"])
    )


def _build_dim_products(
    products: DataFrame,
    productlines: DataFrame,
    product_ids: DataFrame,
) -> DataFrame:
    return (
        products
        .join(productlines, on="productLine", how="left")
        .join(
            product_ids,
            products["productCode"] == product_ids["product_id"],
            "inner",
        )
        .select(
            F.col("productCode").cast("string").alias("product_id"),
            F.col("productName").cast("string").alias("product_name"),
            F.col("productLine").cast("string").alias("product_line"),
            F.col("productVendor").cast("string").alias("product_vendor"),
        )
        .dropDuplicates(["product_id"])
    )


def _build_dim_dates(orders_delta: DataFrame) -> DataFrame:
    order_dates = (
        orders_delta
        .select(F.to_date(F.col("orderDate")).alias("full_date"))
        .dropna()
    )

    return (
        order_dates
        .dropDuplicates(["full_date"])
        .withColumn("year", F.year("full_date").cast("int"))
        .withColumn("quarter", F.quarter("full_date").cast("int"))
        .withColumn("month", F.month("full_date").cast("int"))
        .withColumn("day", F.dayofmonth("full_date").cast("int"))
        .withColumn(
            "date_key",
            F.date_format("full_date", "yyyyMMdd").cast("int"),
        )
        .select(
            "date_key",
            "full_date",
            "year",
            "quarter",
            "month",
            "day",
        )
        .dropDuplicates(["date_key"])
    )


def _customer_territories(
    customers: DataFrame,
    customer_ids: DataFrame,
    employees: DataFrame,
    offices: DataFrame,
) -> DataFrame:
    return (
        customers
        .join(
            customer_ids,
            customers["customerNumber"] == customer_ids["customer_id"],
            "inner",
        )
        .select(
            F.col("customerNumber").cast("int").alias("customer_id"),
            F.col("country").cast("string").alias("country"),
            F.col("salesRepEmployeeNumber")
            .cast("int")
            .alias("sales_rep_employee_number"),
        )
        .join(
            employees.select(
                F.col("employeeNumber").cast("int").alias("employee_number"),
                F.col("officeCode").cast("string").alias("office_code"),
            ),
            on=F.col("sales_rep_employee_number")
            == F.col("employee_number"),
            how="left",
        )
        .join(
            offices.select(
                F.col("officeCode")
                .cast("string")
                .alias("office_code_office"),
                F.col("territory").cast("string").alias("territory"),
            ),
            on=F.col("office_code") == F.col("office_code_office"),
            how="left",
        )
        .select("customer_id", "country", "territory")
    )


def _build_dim_countries(cust_with_territory: DataFrame) -> DataFrame:
    return (
        cust_with_territory
        .select("country", "territory")
        .dropna(subset=["country"])
        .dropDuplicates(["country", "territory"])
        .withColumn(
            "country_key",
            F.xxhash64(F.col("country")).cast("long"),
        )
        .select("country_key", "country", "territory")
        .dropDuplicates(["country_key"])
    )


# ============================================================================
# Public API
# ============================================================================

def build_dimensions(
    *,
    orders_delta: DataFrame,
    orderdetails_delta: DataFrame,
    customers: DataFrame,
    products: DataFrame,
    productlines: DataFrame,
    employees: DataFrame,
    offices: DataFrame,
) -> dict[str, DataFrame]:

    customer_ids = _customer_ids(orders_delta)
    product_ids = _product_ids(orderdetails_delta)

    cust_with_territory = _customer_territories(
        customers,
        customer_ids,
        employees,
        offices,
    )

    return {
        "dim_customers": _build_dim_customers(
            customers,
            customer_ids,
        ),
        "dim_products": _build_dim_products(
            products,
            productlines,
            product_ids,
        ),
        "dim_dates": _build_dim_dates(orders_delta),
        "dim_countries": _build_dim_countries(
            cust_with_territory,
        ),
    }


def build_fact_orders(
    *,
    orderdetails_delta: DataFrame,
    orders_delta: DataFrame,
    customers: DataFrame,
) -> DataFrame:

    fact_orders_base = (
        orderdetails_delta
        .join(orders_delta, on="orderNumber", how="inner")
        .join(
            customers.select("customerNumber", "country"),
            on="customerNumber",
            how="left",
        )
        .select(
            F.col("orderNumber").cast("int").alias("order_id"),
            F.col("customerNumber").cast("int").alias("customer_id"),
            F.col("productCode").cast("string").alias("product_id"),
            F.to_date(F.col("orderDate")).alias("order_date"),
            F.col("country").cast("string").alias("country"),
            F.col("quantityOrdered").cast("int").alias("quantity_ordered"),
            F.col("priceEach").cast("double").alias("price_each"),
        )
    )

    return (
        fact_orders_base
        .withColumn(
            "order_date_key",
            F.date_format("order_date", "yyyyMMdd").cast("int"),
        )
        .withColumn(
            "country_key",
            F.xxhash64(F.col("country")).cast("long"),
        )
        .withColumn(
            "sales_amount",
            (F.col("quantity_ordered") * F.col("price_each"))
            .cast("double"),
        )
        .withColumn("order_year", F.year("order_date").cast("int"))
        .withColumn("order_month", F.month("order_date").cast("int"))
        .select(
            "order_id",
            "customer_id",
            "product_id",
            "order_date_key",
            "country_key",
            "quantity_ordered",
            "price_each",
            "sales_amount",
            "order_year",
            "order_month",
        )
    )