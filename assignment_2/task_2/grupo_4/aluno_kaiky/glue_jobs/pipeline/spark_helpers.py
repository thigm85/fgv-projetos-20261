"""Small Spark helpers shared by pipeline stages."""

from __future__ import annotations

from pyspark.sql import DataFrame


def is_empty(df: DataFrame) -> bool:
    """True when the DataFrame has no rows (cheaper than rdd.isEmpty())."""
    return len(df.take(1)) == 0
