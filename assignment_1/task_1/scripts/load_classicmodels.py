#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import time

import pymysql
from pymysql.err import MySQLError, OperationalError

from common import (
    ConfigError,
    DEFAULT_ENV_FILE,
    DEFAULT_SQL_FILE,
    get_int_env,
    load_env_file,
    require_env,
    resolve_env_path,
)
from sql_utils import INSERT_RE, count_insert_rows, expected_row_counts_from_sql, split_sql_statements


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Cria e popula o banco classicmodels no MySQL do Amazon RDS."
    )
    parser.add_argument(
        "--env-file",
        default=str(DEFAULT_ENV_FILE),
        help="Caminho para o arquivo .env.",
    )
    parser.add_argument(
        "--sql-file",
        default=str(DEFAULT_SQL_FILE),
        help="Caminho para o arquivo SQL com o dataset classicmodels.",
    )
    parser.add_argument(
        "--wait-timeout",
        type=int,
        default=300,
        help="Tempo máximo de espera, em segundos, até o MySQL aceitar conexões.",
    )
    return parser.parse_args()


def connect_mysql(
    *,
    host: str,
    port: int,
    user: str,
    password: str,
    database: str | None = None,
):
    return pymysql.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
        charset="utf8mb4",
        connect_timeout=10,
        read_timeout=120,
        write_timeout=120,
        autocommit=True,
    )


def wait_for_mysql(
    *,
    host: str,
    port: int,
    user: str,
    password: str,
    timeout_seconds: int,
):
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None

    while time.monotonic() < deadline:
        try:
            return connect_mysql(
                host=host,
                port=port,
                user=user,
                password=password,
                database=None,
            )
        except OperationalError as exc:
            last_error = exc
            print(
                f"[wait] MySQL ainda indisponivel em {host}:{port}. "
                "Nova tentativa em 10s."
            )
            time.sleep(10)

    raise RuntimeError(
        f"Timed out waiting for MySQL at {host}:{port} after {timeout_seconds}s."
    ) from last_error


def describe_statement(statement: str) -> str:
    normalized = statement.strip()
    lowered = normalized.lower()

    if lowered.startswith("create database"):
        return "CREATE DATABASE"
    if lowered.startswith("use "):
        return "USE DATABASE"
    if lowered.startswith("drop table"):
        return f"DROP TABLE {normalized.split()[-1]}"
    if lowered.startswith("create table"):
        return f"CREATE TABLE {normalized.split()[2]}"

    insert_match = INSERT_RE.match(normalized)
    if insert_match:
        table = insert_match.group("table")
        rows = count_insert_rows(normalized)
        return f"INSERT {rows} rows into {table}"

    if lowered.startswith("set "):
        return "SET SESSION OPTION"

    return normalized.splitlines()[0][:80]


def execute_sql_script(connection, sql_file) -> int:
    script = sql_file.read_text(encoding="utf-8", errors="ignore")
    statements = split_sql_statements(script)

    with connection.cursor() as cursor:
        for index, statement in enumerate(statements, start=1):
            print(f"[{index}/{len(statements)}] {describe_statement(statement)}")
            cursor.execute(statement)

    return len(statements)


def main() -> int:
    args = parse_args()
    env_file = resolve_env_path(args.env_file)
    sql_file = resolve_env_path(args.sql_file)
    load_env_file(env_file)

    try:
        config = require_env(
            ["MYSQL_HOST", "MYSQL_USER", "MYSQL_PASSWORD", "MYSQL_DATABASE"]
        )
        if not sql_file.exists():
            raise ConfigError(f"SQL file not found: {sql_file}")

        port = get_int_env("MYSQL_PORT", 3306)
        connection = wait_for_mysql(
            host=config["MYSQL_HOST"],
            port=port,
            user=config["MYSQL_USER"],
            password=config["MYSQL_PASSWORD"],
            timeout_seconds=args.wait_timeout,
        )
        print(f"[mysql] Connected to {config['MYSQL_HOST']}:{port}.")
        executed_statements = execute_sql_script(connection, sql_file)
        connection.close()

        expected_counts = expected_row_counts_from_sql(sql_file)
        print(f"[load] Executed {executed_statements} SQL statements.")
        print("[load] Expected rows by table:")
        for table in sorted(expected_counts):
            print(f"  {table}: {expected_counts[table]}")
        return 0
    except (ConfigError, MySQLError, RuntimeError) as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

