"""Load database connection settings from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from utils.rds_discovery import fill_db_host_if_missing

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_ENV_PATH = _PROJECT_ROOT / ".env"

PIPELINE_NAME = "classicmodels_sales"
WATERMARK_TABLE = "etl_watermark"
STATUS_NEVER_RUN = "NEVER_RUN"


@dataclass(frozen=True)
class Settings:
    """MySQL connection settings for the classicmodels OLTP database."""

    db_host: str
    db_port: int
    db_name: str
    db_user: str
    db_password: str
    mysql_connect_retries: int
    mysql_connect_delay_seconds: int
    default_simulate_count: int


def load_settings() -> Settings:
    """Load .env; if DB_HOST is empty, resolve it from AWS once and reload."""
    load_dotenv(_ENV_PATH)

    if not os.getenv("DB_HOST", "").strip():
        fill_db_host_if_missing(_ENV_PATH)
        load_dotenv(_ENV_PATH, override=True)

    return Settings(
        db_host=os.getenv("DB_HOST", "").strip(),
        db_port=int(os.getenv("DB_PORT", "3306")),
        db_name=os.getenv("DB_NAME", "classicmodels"),
        db_user=os.getenv("DB_USER", "admin"),
        db_password=os.getenv("DB_PASSWORD", ""),
        mysql_connect_retries=int(os.getenv("MYSQL_CONNECT_RETRIES", "5")),
        mysql_connect_delay_seconds=int(os.getenv("MYSQL_CONNECT_DELAY_SECONDS", "5")),
        default_simulate_count=int(os.getenv("SIMULATE_ORDER_COUNT", "5")),
    )


def project_root() -> Path:
    return _PROJECT_ROOT
