"""Dimension: country + territory (from offices when available)."""

from __future__ import annotations

import logging

from pyspark.sql import DataFrame
from pyspark.sql import functions as F
from pyspark.sql.window import Window


def build_dim_countries(
    customers: DataFrame,
    offices: DataFrame,
    logger: logging.Logger,
) -> DataFrame:
    logger.info("Building dim_countries")
    countries = customers.select(F.trim(F.col("country")).alias("country")).distinct()
    terr = offices.groupBy(F.trim(F.col("country")).alias("country")).agg(
        F.max(F.col("territory")).alias("territory")
    )
    merged = countries.join(terr, on="country", how="left").withColumn(
        "territory", F.coalesce(F.col("territory"), F.lit("Unknown"))
    )
    w = Window.orderBy(F.col("country"))
    return merged.withColumn("country_key", F.row_number().over(w)).select(
        "country_key", "country", "territory"
    )
