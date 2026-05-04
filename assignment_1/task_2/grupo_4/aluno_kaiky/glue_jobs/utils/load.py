"""
Load layer: write star-schema tables to S3 as Parquet (one prefix per entity).
"""

from __future__ import annotations

import logging
from typing import Dict

from pyspark.sql import DataFrame

from constants import STAR_SCHEMA_OUTPUT_TABLES


def write_parquet_table(
    df: DataFrame,
    base_path: str,
    table_name: str,
    logger: logging.Logger,
    repartition: int = 4,
) -> None:
    path = base_path.rstrip("/") + f"/{table_name}/"
    logger.info("Loading %s to %s", table_name, path)
    (
        df.repartition(repartition)
        .write.mode("overwrite")
        .format("parquet")
        .option("compression", "snappy")
        .save(path)
    )


def load_all_star_schema(
    tables: Dict[str, DataFrame],
    s3_output_path: str,
    logger: logging.Logger,
) -> None:
    missing = set(STAR_SCHEMA_OUTPUT_TABLES) - set(tables.keys())
    if missing:
        raise ValueError(f"Missing tables to load: {missing}")
    for name in STAR_SCHEMA_OUTPUT_TABLES:
        write_parquet_table(tables[name], s3_output_path, name, logger)
