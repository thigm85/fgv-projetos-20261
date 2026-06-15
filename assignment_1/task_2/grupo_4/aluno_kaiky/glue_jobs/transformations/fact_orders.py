"""
Fact table at order-line grain: orderdetails + orders + geography.
product_id follows the sample DB natural key (productCode string).
"""

from __future__ import annotations

import logging

from pyspark.sql import DataFrame
from pyspark.sql import functions as F


def build_fact_orders(
    orderdetails: DataFrame,
    orders: DataFrame,
    customers: DataFrame,
    dim_countries: DataFrame,
    logger: logging.Logger,
) -> DataFrame:
    logger.info("Building fact_orders")
    cust = customers.select(
        F.col("customerNumber").alias("customer_id"),
        F.trim(F.col("country")).alias("country"),
    )
    hdr = orders.join(cust, orders["customerNumber"] == cust["customer_id"], how="inner").select(
        orders["orderNumber"],
        orders["orderDate"],
        orders["customerNumber"],
        cust["country"],
    )
    lines = orderdetails.join(hdr, on="orderNumber", how="inner")
    lines = lines.join(dim_countries, on="country", how="inner")
    qty = F.col("quantityOrdered").cast("decimal(18,4)")
    price = F.col("priceEach").cast("decimal(18,4)")
    sales = (qty * price).cast("decimal(18,4)")
    return lines.select(
        F.col("orderNumber").cast("int").alias("order_id"),
        F.col("customerNumber").cast("int").alias("customer_id"),
        F.col("productCode").alias("product_id"),
        F.date_format(F.col("orderDate"), "yyyyMMdd").cast("int").alias("order_date_key"),
        F.col("country_key").cast("int").alias("country_key"),
        F.col("quantityOrdered").cast("int").alias("quantity_ordered"),
        F.col("priceEach").cast("decimal(18,4)").alias("price_each"),
        sales.alias("sales_amount"),
    )
