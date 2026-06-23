"""Calendar dimension from distinct order dates."""

from __future__ import annotations

import logging

from pyspark.sql import DataFrame
from pyspark.sql import functions as F


def build_dim_dates(orders: DataFrame, logger: logging.Logger) -> DataFrame:
    logger.info("Building dim_dates")
    d = orders.select(F.col("orderDate").alias("full_date")).where(F.col("full_date").isNotNull()).distinct()
    return d.select(
        F.date_format("full_date", "yyyyMMdd").cast("int").alias("date_key"),
        F.col("full_date").alias("full_date"),
        F.year("full_date").alias("year"),
        F.quarter("full_date").alias("quarter"),
        F.month("full_date").alias("month"),
        F.dayofmonth("full_date").alias("day"),
    ).dropDuplicates(["date_key"])
