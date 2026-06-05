from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import pymysql
from pymysql.connections import Connection

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None


PIPELINE_NAME = "classicmodels_sales"
SOLUTION_LABEL = "antonio_brych"
BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"


def load_environment() -> None:
    if load_dotenv is not None and ENV_PATH.exists():
        load_dotenv(ENV_PATH)


def require_env(name: str) -> str:
    value = os.getenv(name)
    if value:
        return value
    raise RuntimeError(f"Variável de ambiente obrigatória ausente: {name}")


@contextmanager
def connect() -> Iterator[Connection]:
    load_environment()
    connection = pymysql.connect(
        host=require_env("DB_HOST"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=require_env("DB_USER"),
        password=require_env("DB_PASSWORD"),
        database=os.getenv("DB_NAME", "classicmodels"),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )
    try:
        yield connection
    finally:
        connection.close()


def fetch_one_value(cursor, sql: str, params: tuple = ()):
    cursor.execute(sql, params)
    row = cursor.fetchone()
    if not row:
        return None
    return next(iter(row.values()))
