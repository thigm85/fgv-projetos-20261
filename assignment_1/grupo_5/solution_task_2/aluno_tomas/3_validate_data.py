#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

import pymysql

from config_utils import load_env_config, section


ROOT = Path(__file__).resolve().parent
CONFIG_DIR = ROOT / "config"
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


def load_json(name: str) -> dict:
    return json.loads((CONFIG_DIR / name).read_text(encoding="utf-8"))


def main() -> int:
    creds = section(load_env_config(), "rds")
    endpoint = load_json("db_endpoint.json")
    conn = pymysql.connect(
        host=endpoint["host"],
        port=int(endpoint["port"]),
        user=creds["db_user"],
        password=creds["db_password"],
        database=endpoint["database"],
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )
    failures: list[str] = []
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = %s
                """,
                (endpoint["database"],),
            )
            tables = {row["TABLE_NAME"] if "TABLE_NAME" in row else row["table_name"] for row in cursor.fetchall()}
            missing = EXPECTED_TABLES - tables
            if missing:
                failures.append("missing tables: " + ", ".join(sorted(missing)))
            for table in sorted(EXPECTED_TABLES & tables):
                cursor.execute(f"SELECT COUNT(*) AS total FROM `{table}`")
                total = cursor.fetchone()["total"]
                print(f"[validate] {table}: {total}")
                if total == 0:
                    failures.append(f"{table} is empty")
    finally:
        conn.close()
    if failures:
        for failure in failures:
            print(f"[validate] FAIL: {failure}")
        return 1
    print("[validate] Source database is ready")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
