"""
Valida se tabelas e volumes basicos foram carregados no classicmodels.

Execute a partir de assignment_1/solution_task_1/:
    python scripts/validate.py [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[1]
ENDPOINT_CACHE_FILE = ROOT_DIR / ".rds_endpoint.json"

EXPECTED_TABLES = {
    "customers",
    "products",
    "productlines",
    "orders",
    "orderdetails",
    "payments",
    "employees",
    "offices",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Valida dados no RDS")
    parser.add_argument("--dry-run", action="store_true", help="Somente imprime SQL")
    return parser.parse_args()


def required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"Variavel obrigatoria ausente: {name}")
    return value


def resolve_endpoint() -> str:
    env_endpoint = os.getenv("RDS_ENDPOINT")
    if env_endpoint:
        return env_endpoint
    if ENDPOINT_CACHE_FILE.exists():
        cache = json.loads(ENDPOINT_CACHE_FILE.read_text(encoding="utf-8"))
        return cache["endpoint"]
    raise ValueError("RDS_ENDPOINT nao definido no .env e cache nao encontrado.")


def ensure_mysql_cli() -> str:
    mysql_bin = shutil.which("mysql")
    if mysql_bin:
        return mysql_bin
    raise RuntimeError(
        "Cliente `mysql` nao encontrado no PATH. Instale o MySQL client e tente novamente. "
        "No macOS (Homebrew): `brew install mysql-client` e adicione "
        "`/opt/homebrew/opt/mysql-client/bin` ao PATH."
    )


def run_query(sql: str) -> str:
    mysql_bin = ensure_mysql_cli()
    cmd = [
        mysql_bin,
        f"--host={resolve_endpoint()}",
        f"--port={required_env('RDS_PORT')}",
        f"--user={required_env('RDS_MASTER_USERNAME')}",
        f"--password={required_env('RDS_MASTER_PASSWORD')}",
        "--batch",
        "--skip-column-names",
        required_env("RDS_DB_NAME"),
        "--execute",
        sql,
    ]
    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def run() -> None:
    load_dotenv(ROOT_DIR / ".env")
    args = parse_args()

    table_sql = "SHOW TABLES;"
    count_sql = "SELECT COUNT(*) FROM customers;"

    if args.dry_run:
        print("Dry-run habilitado.")
        print(f"SQL tabelas: {table_sql}")
        print(f"SQL contagem: {count_sql}")
        return

    print("Validando tabelas...")
    table_output = run_query(table_sql)
    found_tables = {line.strip() for line in table_output.splitlines() if line.strip()}

    missing = sorted(EXPECTED_TABLES - found_tables)
    extra = sorted(found_tables - EXPECTED_TABLES)
    if missing:
        raise RuntimeError(f"Tabelas esperadas ausentes: {missing}")
    if extra:
        print(f"Aviso: tabelas extras encontradas: {extra}")

    print("Validando volume minimo de dados...")
    customers_count = int(run_query(count_sql))
    if customers_count <= 0:
        raise RuntimeError("Tabela customers sem registros.")

    print("Validacao concluida com sucesso.")
    print(f"Tabelas encontradas: {len(found_tables)} | customers: {customers_count}")


if __name__ == "__main__":
    run()
