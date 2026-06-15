"""Validate business rules on the incremental delta before committing the watermark."""

from __future__ import annotations

from constants import SALES_TOLERANCE, STAR_REFERENTIAL_KEYS
from pipeline.spark_helpers import is_empty
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F


def validate_delta(*, spark: SparkSession, delta_fact: DataFrame, dims: dict[str, DataFrame]) -> None:
    if is_empty(delta_fact):
        return

    bad_sales = delta_fact.filter(
        F.abs(F.col("sales_amount") - (F.col("quantity_ordered") * F.col("price_each"))) > SALES_TOLERANCE
    )
    if bad_sales.take(1):
        raise ValueError("sales_amount rule violated in delta fact_orders")

    for fk_col, dim_name, dim_key in STAR_REFERENTIAL_KEYS:
        dim_keys = dims[dim_name].select(dim_key).distinct()
        orphans = delta_fact.join(dim_keys, delta_fact[fk_col] == dim_keys[dim_key], "left_anti")
        if orphans.take(1):
            raise ValueError(f"FK orphan: fact_orders.{fk_col} not in {dim_name}.{dim_key}")
