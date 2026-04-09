"""
Cria o schema classicmodels e carrega dados via CLI mysql.

Execute a partir de assignment_1/solution_task_1/:
    python scripts/load_data.py [--dry-run]
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
SQL_FILE = ROOT_DIR / "data" / "mysqlsampledatabase.sql"
ENDPOINT_CACHE_FILE = ROOT_DIR / ".rds_endpoint.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Carga de dados no RDS")
    parser.add_argument("--dry-run", action="store_true", help="Apenas imprime comando")
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


def build_mysql_command() -> list[str]:
    endpoint = resolve_endpoint()
    username = required_env("RDS_MASTER_USERNAME")
    password = required_env("RDS_MASTER_PASSWORD")
    port = required_env("RDS_PORT")
    db_name = required_env("RDS_DB_NAME")

    sql = f"DROP DATABASE IF EXISTS {db_name}; CREATE DATABASE {db_name};"
    return [
        "mysql",
        f"--host={endpoint}",
        f"--port={port}",
        f"--user={username}",
        f"--password={password}",
        "--execute",
        sql,
    ]


def ensure_mysql_cli() -> str:
    mysql_bin = shutil.which("mysql")
    if mysql_bin:
        return mysql_bin
    raise RuntimeError(
        "Cliente `mysql` nao encontrado no PATH. Instale o MySQL client e tente novamente. "
        "No macOS (Homebrew): `brew install mysql-client` e adicione "
        "`/opt/homebrew/opt/mysql-client/bin` ao PATH."
    )


def run() -> None:
    load_dotenv(ROOT_DIR / ".env")
    args = parse_args()

    if not SQL_FILE.exists():
        raise FileNotFoundError(f"Arquivo SQL nao encontrado: {SQL_FILE}")

    mysql_bin = ensure_mysql_cli()
    setup_cmd = build_mysql_command()
    setup_cmd[0] = mysql_bin
    import_cmd = [
        mysql_bin,
        f"--host={resolve_endpoint()}",
        f"--port={required_env('RDS_PORT')}",
        f"--user={required_env('RDS_MASTER_USERNAME')}",
        f"--password={required_env('RDS_MASTER_PASSWORD')}",
        required_env("RDS_DB_NAME"),
    ]

    if args.dry_run:
        print("Dry-run habilitado.")
        print("Comando de setup:")
        print(" ".join(setup_cmd))
        print("Comando de import:")
        print(" ".join(import_cmd) + f" < {SQL_FILE}")
        return

    print("Criando schema...")
    subprocess.run(setup_cmd, check=True)
    print("Carregando dump SQL...")
    with SQL_FILE.open("rb") as sql_file:
        subprocess.run(import_cmd, check=True, stdin=sql_file)
    print("Carga concluida com sucesso.")


if __name__ == "__main__":
    run()
