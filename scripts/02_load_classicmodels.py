#!/usr/bin/env python3
"""Carrega classicmodels no MySQL lendo apenas .env."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pymysql


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


def split_sql_statements(script: str) -> list[str]:
    statements: list[str] = []
    buf: list[str] = []
    in_single = False
    in_double = False
    in_backtick = False
    escaped = False

    for char in script:
        buf.append(char)

        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if not in_double and not in_backtick and char == "'":
            in_single = not in_single
            continue
        if not in_single and not in_backtick and char == '"':
            in_double = not in_double
            continue
        if not in_single and not in_double and char == "`":
            in_backtick = not in_backtick
            continue
        if char == ";" and not in_single and not in_double and not in_backtick:
            stmt = "".join(buf).strip()
            if stmt:
                statements.append(stmt)
            buf = []

    tail = "".join(buf).strip()
    if tail:
        statements.append(tail)
    return statements


def main() -> int:
    load_dotenv()

    host = env("MYSQL_HOST", required=True)
    port = int(env("MYSQL_PORT", "3306"))
    user = env("MYSQL_USER", "admin")
    password = env("MYSQL_PASSWORD", required=True)
    sql_file = env("MYSQL_SQL_FILE", "assignment_1/task_1/data/mysqlsampledatabase.sql")

    path = Path(sql_file)
    if not path.exists():
        print(f"Arquivo SQL não encontrado: {path}", file=sys.stderr)
        return 1

    statements = split_sql_statements(path.read_text(encoding="utf-8"))
    if not statements:
        print("Nenhum statement SQL encontrado.", file=sys.stderr)
        return 1

    conn = pymysql.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        charset="utf8mb4",
        autocommit=False,
        cursorclass=pymysql.cursors.Cursor,
    )

    try:
        with conn.cursor() as cursor:
            total = len(statements)
            for i, stmt in enumerate(statements, start=1):
                cursor.execute(stmt)
                if i % 100 == 0 or i == total:
                    print(f"Executados {i}/{total} statements")
        conn.commit()
    except Exception as exc:
        conn.rollback()
        print(f"Erro no load: {exc}", file=sys.stderr)
        return 1
    finally:
        conn.close()

    print("Carga concluída.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
