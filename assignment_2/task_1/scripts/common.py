from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import pymysql
from pymysql.connections import Connection

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None


PIPELINE_NAME = "classicmodels_sales"
BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"


def load_environment() -> None:
    if load_dotenv is not None and ENV_PATH.exists():
        load_dotenv(ENV_PATH)


def require_env(name: str) -> str:
    value = os.getenv(name)
    if value:
        return value
    raise RuntimeError(f"Missing required environment variable: {name}")


def get_database_value(primary_name: str, fallback_name: str | None = None) -> str:
    value = os.getenv(primary_name)
    if value:
        return value
    if fallback_name:
        fallback = os.getenv(fallback_name)
        if fallback:
            return fallback
    raise RuntimeError(f"Missing required environment variable: {primary_name}")


def ssl_config() -> dict[str, str] | None:
    ssl_ca = os.getenv("DB_SSL_CA")
    if not ssl_ca:
        return None

    ssl_ca_path = Path(ssl_ca)
    if not ssl_ca_path.is_absolute():
        ssl_ca_path = BASE_DIR / ssl_ca_path

    if not ssl_ca_path.exists():
        raise RuntimeError(f"DB_SSL_CA does not exist: {ssl_ca_path}")

    return {"ca": str(ssl_ca_path), "check_hostname": True}


@contextmanager
def connect() -> Iterator[Connection]:
    load_environment()
    connection = pymysql.connect(
        host=get_database_value("DB_HOST", "MYSQL_HOST"),
        port=int(os.getenv("DB_PORT") or os.getenv("MYSQL_PORT", "3306")),
        user=get_database_value("DB_USER", "MYSQL_USER"),
        password=get_database_value("DB_PASSWORD", "MYSQL_PASSWORD"),
        database=os.getenv("DB_NAME") or os.getenv("MYSQL_DATABASE", "classicmodels"),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
        ssl=ssl_config(),
    )
    try:
        yield connection
    finally:
        connection.close()


def fetch_one_value(cursor: Any, sql: str, params: tuple[Any, ...] = ()) -> Any:
    cursor.execute(sql, params)
    row = cursor.fetchone()
    if row is None:
        return None
    return next(iter(row.values()))
