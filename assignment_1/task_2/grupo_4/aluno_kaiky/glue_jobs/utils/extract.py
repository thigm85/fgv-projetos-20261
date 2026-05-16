"""
Extract layer: read OLTP tables from MySQL (RDS) via Glue JDBC connection.
Credentials stay in the Glue connection — not in code or job arguments.
"""

from __future__ import annotations

import logging
from typing import Dict

from awsglue.context import GlueContext
from pyspark.sql import DataFrame

from constants import SOURCE_TABLES


def read_mysql_table(
    glue_context: GlueContext,
    connection_name: str,
    database: str,
    table: str,
    logger: logging.Logger,
) -> DataFrame:
    """
    Load a single table using the configured Glue connection (MySQL).
    The Glue connection JDBC URL must include the catalog (e.g. .../classicmodels);
    ``dbtable`` is then only the table name (avoids duplicate catalog in the path).
    """
    logger.info(
        "Extracting %s.%s via connection %s", database, table, connection_name
    )
    dyf = glue_context.create_dynamic_frame_from_options(
        connection_type="mysql",
        connection_options={
            "useConnectionProperties": "true",
            "connectionName": connection_name,
            "dbtable": table,
        },
    )
    return dyf.toDF()


def extract_all(
    glue_context: GlueContext,
    connection_name: str,
    database: str,
    logger: logging.Logger,
) -> Dict[str, DataFrame]:
    """
    Returns raw DataFrames keyed by lowercase table name.
    Includes `offices` only to derive territory in dim_countries (not required as Parquet output).
    """
    out: Dict[str, DataFrame] = {}
    for t in SOURCE_TABLES:
        out[t] = read_mysql_table(glue_context, connection_name, database, t, logger)
    return out
