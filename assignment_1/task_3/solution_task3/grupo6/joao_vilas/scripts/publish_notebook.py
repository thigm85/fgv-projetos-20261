from __future__ import annotations

import logging
import sys
from pathlib import Path

import boto3

from config import load_config


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger(__name__)


NOTEBOOK_KEY = "notebooks/classicmodels_dashboard.ipynb"


def main() -> int:
    config = load_config()
    notebook_path = Path(__file__).resolve().parents[1] / "notebooks" / "classicmodels_dashboard.ipynb"

    if not notebook_path.exists():
        logger.error("Notebook nao encontrado: %s", notebook_path)
        return 1

    s3 = boto3.client("s3", region_name=config.aws_region)
    logger.info("Subindo %s para s3://%s/%s", notebook_path, config.etl_bucket, NOTEBOOK_KEY)

    s3.upload_file(str(notebook_path), config.etl_bucket, NOTEBOOK_KEY)
    logger.info("Notebook publicado")
    return 0


if __name__ == "__main__":
    sys.exit(main())
