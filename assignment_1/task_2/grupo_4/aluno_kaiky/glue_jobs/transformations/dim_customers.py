"""Dimension: customers (denormalized contact name)."""

from __future__ import annotations

import logging

from pyspark.sql import DataFrame
from pyspark.sql import functions as F


def build_dim_customers(customers: DataFrame, logger: logging.Logger) -> DataFrame:
    logger.info("Building dim_customers")
    contact = F.trim(F.col("contactFirstName"))
    last = F.trim(F.col("contactLastName"))
    contact_name = F.trim(F.concat_ws(" ", contact, last))
    return customers.select(
        F.col("customerNumber").cast("int").alias("customer_id"),
        F.col("customerName").alias("customer_name"),
        contact_name.alias("contact_name"),
        F.col("city").alias("city"),
        F.trim(F.col("country")).alias("country"),
    ).dropDuplicates(["customer_id"])
