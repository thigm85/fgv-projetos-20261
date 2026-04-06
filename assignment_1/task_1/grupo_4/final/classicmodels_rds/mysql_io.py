"""MySQL connection, multi-statement SQL file load, and classicmodels validation."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import mysql.connector
from mysql.connector import errors as mysql_errors

from classicmodels_rds.config import Settings

EXPECTED_TABLES: tuple[str, ...] = (
    "customers",
    "products",
    "productlines",
    "orders",
    "orderdetails",
    "payments",
    "employees",
    "offices",
)


def connect_with_retries(settings: Settings):
    """Connect to MySQL with backoff (RDS may reject briefly after provisioning)."""
    if not settings.db_host:
        print(
            "DB_HOST is empty. Run scripts/01_provision_rds.py first "
            "or set DB_HOST in .env / connection.local.env.",
            file=sys.stderr,
        )
        sys.exit(1)

    last_err: Exception | None = None
    for attempt in range(1, settings.mysql_connect_retries + 1):
        try:
            conn = mysql.connector.connect(
                host=settings.db_host,
                user=settings.db_user,
                password=settings.db_password,
                port=settings.db_port,
                connection_timeout=15,
                autocommit=True,
                ssl_disabled=True,
                use_pure=True,
            )
            print(f"[MySQL] Connected  host={settings.db_host}  user={settings.db_user}")
            return conn
        except mysql_errors.Error as exc:
            last_err = exc
            if attempt == settings.mysql_connect_retries:
                break
            print(
                f"[MySQL] Attempt {attempt}/{settings.mysql_connect_retries}: {exc}. "
                f"Retrying in {settings.mysql_connect_delay_seconds}s ..."
            )
            time.sleep(settings.mysql_connect_delay_seconds)

    print(f"[MySQL] Could not connect: {last_err}", file=sys.stderr)
    raise last_err


def run_sql_file(conn, sql_path: Path) -> None:
    if not sql_path.is_file():
        raise FileNotFoundError(f"SQL file not found: {sql_path}")

    sql_text = sql_path.read_text(encoding="utf-8", errors="replace")
    print(f"[MySQL] Executing {sql_path} (cmd_query_iter, multi-statement) ...")
    n = 0
    for result in conn.cmd_query_iter(sql_text):
        if result.get("columns"):
            conn.get_rows()
        n += 1
        if n % 200 == 0:
            print(f"  ... {n} statement result(s) so far")
    print(f"[MySQL] SQL file finished ({n} statement result(s)).")


def table_row_counts(conn, database: str) -> dict[str, int]:
    """Return row counts for EXPECTED_TABLES in `database`."""
    out: dict[str, int] = {}
    cursor = conn.cursor()
    try:
        for table in EXPECTED_TABLES:
            cursor.execute(
                f"SELECT COUNT(*) FROM `{database}`.`{table}`",
            )
            row = cursor.fetchone()
            out[table] = int(row[0]) if row else 0
    finally:
        cursor.close()
    return out


def validate_classicmodels(conn, settings: Settings) -> bool:
    """
    Ensure all expected tables exist with at least one row.
    Prints a short report; returns True if all checks pass.
    """
    db = settings.db_name
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT TABLE_NAME FROM information_schema.TABLES "
            "WHERE TABLE_SCHEMA = %s AND TABLE_TYPE = 'BASE TABLE'",
            (db,),
        )
        existing = {r[0] for r in cursor.fetchall()}
    finally:
        cursor.close()

    missing = [t for t in EXPECTED_TABLES if t not in existing]
    if missing:
        print(f"[validate] Missing tables in `{db}`: {missing}")
        return False

    counts = table_row_counts(conn, db)
    print(f"[validate] Database `{db}` — row counts:")
    ok = True
    for name in EXPECTED_TABLES:
        n = counts.get(name, 0)
        status = "ok" if n > 0 else "FAIL (zero rows)"
        if n <= 0:
            ok = False
        print(f"  {name:16}  {n:8}  {status}")
    return ok
