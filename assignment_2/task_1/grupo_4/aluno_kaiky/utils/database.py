"""MySQL connection helpers with simple retry logic."""

from __future__ import annotations
import time
from contextlib import contextmanager
from typing import Any, Generator, Iterable
import pymysql
from pymysql.connections import Connection
from pymysql.cursors import DictCursor
from utils.config import Settings, load_settings


def _validate_settings(settings: Settings) -> None:
    required = {
        "DB_HOST": settings.db_host,
        "DB_PASSWORD": settings.db_password,
    }

    missing = [key for key, value in required.items() if not value]

    if missing:
        raise ValueError(
            f"Missing required environment variables: {', '.join(missing)}"
        )

def _create_connection(settings: Settings) -> Connection:
    return pymysql.connect(
        host=settings.db_host,
        port=settings.db_port,
        user=settings.db_user,
        password=settings.db_password,
        database=settings.db_name,
        charset="utf8mb4",
        cursorclass=DictCursor,
        autocommit=False,
    )

def connect(settings: Settings | None = None) -> Connection:
    """
    Open a PyMySQL connection to classicmodels.
    Retries a few times to tolerate brief RDS startup or network blips.
    """
    settings = settings or load_settings()
    _validate_settings(settings)

    for attempt in range(settings.mysql_connect_retries):
        try:
            return _create_connection(settings)
        except pymysql.MySQLError as exc:
            if attempt == settings.mysql_connect_retries - 1:
                raise ConnectionError(
                    f"Could not connect to MySQL at "
                    f"{settings.db_host}:{settings.db_port}: {exc}"
                ) from exc

            time.sleep(settings.mysql_connect_delay_seconds)


@contextmanager
def db_session(settings: Settings | None = None) -> Generator[Connection, None, None]:
    """Context manager that always closes the connection."""
    conn = connect(settings)
    try:
        yield conn
    finally:
        conn.close()


def fetch_one(conn: Connection, sql: str, params: Iterable[Any] | None = None) -> dict | None:
    """Run a query and return the first row as a dict, or None."""
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()


def fetch_all(conn: Connection, sql: str, params: Iterable[Any] | None = None) -> list[dict]:
    """Run a query and return all rows as dicts."""
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return list(cur.fetchall())


def execute(conn: Connection, sql: str, params: Iterable[Any] | None = None) -> int:
    """Execute a statement and return affected row count."""
    with conn.cursor() as cur:
        affected = cur.execute(sql, params)
    return affected
