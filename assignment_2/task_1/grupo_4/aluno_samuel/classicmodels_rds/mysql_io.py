"""MySQL connection, multi-statement SQL file load, and classicmodels validation."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import mysql.connector
from mysql.connector import errors as mysql_errors
from mysql.connector import Error

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


def table_existence(conn, database: str) -> dict[str, bool]:
    """Return whether each EXPECTED_TABLE exists in `database`."""
    out: dict[str, bool] = {}
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT TABLE_NAME
            FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_SCHEMA = %s AND TABLE_TYPE = 'BASE TABLE'
        """, (database,))
        
        existing_tables = {row[0] for row in cursor.fetchall()}

        for table in EXPECTED_TABLES:
            out[table] = table in existing_tables

    finally:
        cursor.close()

    return out


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


def table_column_info(conn, database: str) -> dict[str, list[dict]]:
    """Return column metadata for EXPECTED_TABLES in `database`."""
    out: dict[str, list[dict]] = {}
    cursor = conn.cursor()
    try:
        for table in EXPECTED_TABLES:
            cursor.execute("""
                SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, COLUMN_KEY
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
                ORDER BY ORDINAL_POSITION
            """, (database, table))

            columns = cursor.fetchall()

            out[table] = [
                {
                    "name": col_name,
                    "type": data_type,
                    "nullable": is_nullable,
                    "key": col_key,
                }
                for col_name, data_type, is_nullable, col_key in columns
            ]
    finally:
        cursor.close()

    return out


def validate_classicmodels(conn, settings: Settings) -> bool:
    """
    Ensure all expected tables exist and print row counts
    and column info.

    Prints a report; returns True if all tables exist and
    have rows, False otherwise.
    """
    db = settings.db_name
    all_ok = True

    print(f"[validate] Database `{db}`")

    existence = table_existence(conn, db)
    row_counts = table_row_counts(conn, db)
    column_info = table_column_info(conn, db)

    # Check missing tables
    missing_tables = [t for t, exists in existence.items() if not exists]
    if missing_tables:
        print(f"[validate] Missing tables: {missing_tables}")
        return False

    for table in EXPECTED_TABLES:
        # Rows
        count = row_counts.get(table, 0)
        status = "OK" if count > 0 else "EMPTY"

        if count == 0:
            all_ok = False

        print(f"\n\nTable: {table} | Rows: {count} | Status: {status}")

        # Columns
        columns = column_info.get(table, [])

        if not columns:
            print("No columns found")
            all_ok = False
            continue

        print(f"{'Column':<25} {'Type':<15} {'Nullable':<10} {'Key':<5}")
        print("-" * 56)

        for col in columns:
            print(
                f"{col['name']:<25} "
                f"{col['type']:<15} "
                f"{col['nullable']:<10} "
                f"{col['key']:<5}"
            )

    print("")
    if all_ok:
        print("[validate] Validation completed: all tables OK.")
    else:
        print("[validate] Validation warning: issues found.")

    return all_ok