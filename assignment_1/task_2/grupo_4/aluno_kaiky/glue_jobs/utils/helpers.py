"""
Argument parsing, logging, and small Spark helpers for the Glue job.
"""

from __future__ import annotations

import logging
import sys
from typing import Any, Dict, List

from awsglue.utils import getResolvedOptions


def get_job_logger(name: str = "classicmodels_etl") -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s — %(message)s")
        )
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger


def parse_job_args(argv: List[str], optional_keys: List[str] | None = None) -> Dict[str, Any]:
    """
    Glue passes mandatory args; optional ones may be omitted in dev.
    """
    optional_keys = optional_keys or []
    required = [
        "JOB_NAME",
        "GLUE_CONNECTION_NAME",
        "S3_OUTPUT_PATH",
        "RDS_DATABASE",
    ]
    return dict(getResolvedOptions(argv, required + optional_keys))


def require_non_empty(df, name: str, logger: logging.Logger) -> None:
    c = df.count()
    if c == 0:
        raise ValueError(f"Validation failed: DataFrame '{name}' is empty.")
    logger.info("Row count %s: %d", name, c)
