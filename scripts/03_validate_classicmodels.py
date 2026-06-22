#!/usr/bin/env python3
"""Valida tabelas e contagens do classicmodels lendo apenas .env."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pymysql

EXPECTED_TABLES = {
    "customers",
    "employees",
    "offices",
    "orderdetails",
    "orders",
    "payments",
    "productlines",
    "products",
}


def load_dotenv(path: str = ".env") -> None:
    env_path = Path(path)
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        entry = line.strip()
        if not entry or entry.startswith("#") or "=" not in entry:
            continue
        key, value = entry.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value


def env(name: str, default: str | None = None, required: bool = False) -> str:
    value = os.getenv(name, default)
    if required and not value:
        raise RuntimeError(f"Variável obrigatória ausente: {name}")
    return value or ""


def main() -> int:
    load_dotenv()

    host = env("MYSQL_HOST", required=True)
    port = int(env("MYSQL_PORT", "3306"))
    user = env("MYSQL_USER", "admin")
    password = env("MYSQL_PASSWORD", required=True)
    database = env("MYSQL_DATABASE", "classicmodels")

    conn = pymysql.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
        charset="utf8mb4",
        autocommit=True,
        cursorclass=pymysql.cursors.DictCursor,
    )

    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = %s
                """,
                (database,),
            )
            rows = cursor.fetchall()
            existing = set()
            for row in rows:
                if "table_name" in row:
                    existing.add(row["table_name"])
                elif "TABLE_NAME" in row:
                    existing.add(row["TABLE_NAME"])
                else:
                    existing.add(next(iter(row.values())))

            missing = EXPECTED_TABLES - existing
            extras = existing - EXPECTED_TABLES

            print("Tabelas encontradas:", ", ".join(sorted(existing)))
            if missing:
                print(f"Faltando: {', '.join(sorted(missing))}", file=sys.stderr)
                return 1
            if extras:
                print(f"Extras: {', '.join(sorted(extras))}")

            for table in sorted(EXPECTED_TABLES):
                cursor.execute(f"SELECT COUNT(*) AS total FROM `{table}`")
                total = cursor.fetchone()["total"]
                print(f"{table}: {total}")

            print("Validação concluída.")
            return 0
    except Exception as exc:
        print(f"Erro na validação: {exc}", file=sys.stderr)
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
