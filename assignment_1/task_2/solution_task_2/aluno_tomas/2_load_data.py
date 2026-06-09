#!/usr/bin/env python3
from __future__ import annotations

import json
import time
from pathlib import Path

import pymysql
from pymysql.err import OperationalError

from config_utils import load_env_config, section


ROOT = Path(__file__).resolve().parent
CONFIG_DIR = ROOT / "config"
SQL_FILE = ROOT.parents[2] / "task_1" / "data" / "mysqlsampledatabase.sql"


def load_json(name: str) -> dict:
    path = CONFIG_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"Missing {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def split_sql(script: str) -> list[str]:
    statements: list[str] = []
    buffer: list[str] = []
    in_single = False
    in_double = False
    escaped = False
    for ch in script:
        buffer.append(ch)
        if escaped:
            escaped = False
            continue
        if ch == "\\":
            escaped = True
            continue
        if ch == "'" and not in_double:
            in_single = not in_single
            continue
        if ch == '"' and not in_single:
            in_double = not in_double
            continue
        if ch == ";" and not in_single and not in_double:
            statement = "".join(buffer).strip()
            if statement:
                statements.append(statement)
            buffer = []
    tail = "".join(buffer).strip()
    if tail:
        statements.append(tail)
    return statements


def connect_with_retry(host: str, port: int, user: str, password: str):
    last_error: Exception | None = None
    for attempt in range(1, 31):
        try:
            return pymysql.connect(
                host=host,
                port=port,
                user=user,
                password=password,
                charset="utf8mb4",
                autocommit=False,
                connect_timeout=10,
                read_timeout=120,
                write_timeout=120,
            )
        except OperationalError as exc:
            last_error = exc
            print(f"[mysql] Waiting for MySQL ({attempt}/30): {exc}")
            time.sleep(10)
    raise RuntimeError("Could not connect to MySQL") from last_error


def main() -> int:
    creds = section(load_env_config(), "rds")
    endpoint = load_json("db_endpoint.json")
    if not SQL_FILE.exists():
        raise FileNotFoundError(f"Missing SQL file: {SQL_FILE}")

    conn = connect_with_retry(
        endpoint["host"],
        int(endpoint["port"]),
        creds["db_user"],
        creds["db_password"],
    )
    statements = split_sql(SQL_FILE.read_text(encoding="utf-8", errors="ignore"))
    try:
        with conn.cursor() as cursor:
            for idx, statement in enumerate(statements, start=1):
                cursor.execute(statement)
                if idx % 50 == 0 or idx == len(statements):
                    print(f"[load] Executed {idx}/{len(statements)} SQL statements")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    print("[load] classicmodels loaded successfully")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
