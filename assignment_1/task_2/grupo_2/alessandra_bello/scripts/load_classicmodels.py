from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

import mysql.connector
from mysql.connector import Error

from common import configure_logging, load_environment, require_env


EXPECTED_TABLES = [
    "customers",
    "products",
    "productlines",
    "orders",
    "orderdetails",
    "payments",
    "employees",
    "offices",
]


def sql_path() -> Path:
    return Path(__file__).resolve().parents[4] / "task_1" / "data" / "mysqlsampledatabase.sql"


def wait_for_connection(host: str, port: int, database: str, user: str, password: str, retries: int = 20, delay_seconds: int = 15):
    last_error: Error | None = None

    for attempt in range(1, retries + 1):
        try:
            logging.info("Tentativa %s/%s de conexao ao MySQL", attempt, retries)
            return mysql.connector.connect(
                host=host,
                port=port,
                user=user,
                password=password,
                database=database,
                autocommit=False,
            )
        except Error as exc:
            last_error = exc
            logging.warning("Conexao falhou: %s", exc)
            time.sleep(delay_seconds)

    raise RuntimeError(f"Nao foi possivel conectar ao MySQL: {last_error}")


def execute_sql_file(connection, file_path: Path) -> None:
    sql_text = file_path.read_text(encoding="utf-8")
    statements = [statement.strip() for statement in sql_text.split(";\n") if statement.strip()]
    cursor = connection.cursor()

    try:
        for statement in statements:
            cursor.execute(statement)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()


def validate_tables(connection) -> list[str]:
    cursor = connection.cursor()
    failures: list[str] = []

    try:
        cursor.execute("SHOW TABLES")
        tables = {row[0] for row in cursor.fetchall()}

        for table_name in EXPECTED_TABLES:
            if table_name not in tables:
                failures.append(f"Tabela ausente: {table_name}")
                continue

            cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            count = cursor.fetchone()[0]
            logging.info("Tabela %s possui %s registros", table_name, count)

            if count <= 0:
                failures.append(f"Tabela vazia: {table_name}")
    finally:
        cursor.close()

    return failures


def main() -> int:
    configure_logging()
    load_environment()

    host = require_env("DB_HOST")
    port = int(require_env("DB_PORT"))
    database = require_env("DB_NAME")
    user = require_env("DB_USER")
    password = require_env("DB_PASSWORD")

    file_path = sql_path()
    if not file_path.exists():
        raise FileNotFoundError(f"Arquivo SQL nao encontrado: {file_path}")

    logging.info("Iniciando carga do schema classicmodels em %s", host)
    connection = wait_for_connection(host, port, database, user, password)

    try:
        execute_sql_file(connection, file_path)
        failures = validate_tables(connection)
    finally:
        connection.close()

    if failures:
        for failure in failures:
            logging.error(failure)
        return 1

    logging.info("Carga e validacao do banco concluida com sucesso")
    return 0


if __name__ == "__main__":
    sys.exit(main())
