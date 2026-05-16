#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys

import pymysql
from pymysql.cursors import DictCursor
from pymysql.err import MySQLError

from common import (
    ConfigError,
    DEFAULT_ENV_FILE,
    DEFAULT_SQL_FILE,
    REQUIRED_TABLES,
    get_int_env,
    load_env_file,
    require_env,
    resolve_env_path,
)
from sql_utils import expected_row_counts_from_sql


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Valida se o banco classicmodels foi criado e populado corretamente."
    )
    parser.add_argument(
        "--env-file",
        default=str(DEFAULT_ENV_FILE),
        help="Caminho para o arquivo .env.",
    )
    parser.add_argument(
        "--sql-file",
        default=str(DEFAULT_SQL_FILE),
        help="Caminho para o arquivo SQL usado como referencia.",
    )
    return parser.parse_args()


def connect_mysql(*, host: str, port: int, user: str, password: str, database: str):
    return pymysql.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
        charset="utf8mb4",
        connect_timeout=10,
        read_timeout=60,
        write_timeout=60,
        cursorclass=DictCursor,
        autocommit=True,
    )


def fetch_tables(connection, database: str) -> set[str]:
    query = """
        SELECT table_name AS table_name
        FROM information_schema.tables
        WHERE table_schema = %s
    """
    with connection.cursor() as cursor:
        cursor.execute(query, (database,))
        tables: set[str] = set()
        for row in cursor.fetchall():
            table_name = row.get("table_name") or row.get("TABLE_NAME")
            if not table_name:
                raise RuntimeError(f"Unexpected row returned by information_schema: {row}")
            tables.add(str(table_name))
        return tables


def fetch_row_count(connection, table: str) -> int:
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT COUNT(*) AS row_count FROM `{table}`")
        row = cursor.fetchone()
    return int(row["row_count"])


def main() -> int:
    args = parse_args()
    env_file = resolve_env_path(args.env_file)
    sql_file = resolve_env_path(args.sql_file)
    load_env_file(env_file)

    try:
        config = require_env(
            ["MYSQL_HOST", "MYSQL_USER", "MYSQL_PASSWORD", "MYSQL_DATABASE"]
        )
        port = get_int_env("MYSQL_PORT", 3306)

        expected_counts: dict[str, int | None] = (
            expected_row_counts_from_sql(sql_file)
            if sql_file.exists()
            else {table: None for table in REQUIRED_TABLES}
        )
        expected_tables = set(expected_counts) or set(REQUIRED_TABLES)

        connection = connect_mysql(
            host=config["MYSQL_HOST"],
            port=port,
            user=config["MYSQL_USER"],
            password=config["MYSQL_PASSWORD"],
            database=config["MYSQL_DATABASE"],
        )

        actual_tables = fetch_tables(connection, config["MYSQL_DATABASE"])
        missing_tables = sorted(expected_tables - actual_tables)
        extra_tables = sorted(actual_tables - expected_tables)

        mismatched_counts: list[tuple[str, int, int]] = []
        actual_counts: dict[str, int] = {}

        for table in sorted(expected_tables):
            if table not in actual_tables:
                continue
            actual_counts[table] = fetch_row_count(connection, table)
            expected = expected_counts.get(table)
            if expected is not None and actual_counts[table] != expected:
                mismatched_counts.append((table, expected, actual_counts[table]))

        connection.close()

        print("[validation] Tables found:")
        for table in sorted(actual_counts):
            print(f"  {table}: {actual_counts[table]} rows")

        if extra_tables:
            print("[validation] Extra tables:")
            for table in extra_tables:
                print(f"  {table}")

        if missing_tables or mismatched_counts:
            if missing_tables:
                print("[validation] Missing tables:", file=sys.stderr)
                for table in missing_tables:
                    print(f"  {table}", file=sys.stderr)
            if mismatched_counts:
                print("[validation] Row count mismatches:", file=sys.stderr)
                for table, expected, actual in mismatched_counts:
                    print(
                        f"  {table}: expected {expected}, found {actual}",
                        file=sys.stderr,
                    )
            return 1

        print(
            f"[validation] Success: schema {config['MYSQL_DATABASE']} "
            "contains all expected tables with the expected row counts."
        )
        return 0
    except (ConfigError, MySQLError, RuntimeError) as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
