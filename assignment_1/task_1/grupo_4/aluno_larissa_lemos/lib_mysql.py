from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

import mysql.connector


@dataclass(frozen=True)
class MySqlConnInfo:
    host: str
    port: int
    user: str
    password: str
    database: Optional[str] = None


def connect(info: MySqlConnInfo) -> mysql.connector.MySQLConnection:
    return mysql.connector.connect(
        host=info.host,
        port=info.port,
        user=info.user,
        password=info.password,
        database=info.database,
        autocommit=False,
    )


def execute_sql_file(*, info: MySqlConnInfo, sql_path: Path) -> None:
    sql_text = sql_path.read_text(encoding="utf-8", errors="replace")
    # mysql-connector-python 9.x: cursor.execute(..., multi=True) was removed;
    # C-extension connections also do not implement cmd_query_iter. Pure-Python
    # MySQLConnection supports cmd_query_iter for multi-statement scripts.
    with mysql.connector.connect(
        host=info.host,
        port=info.port,
        user=info.user,
        password=info.password,
        database=info.database,
        autocommit=False,
        use_pure=True,
    ) as conn:
        for result in conn.cmd_query_iter(sql_text):
            if "columns" in result:
                conn.get_rows()
        conn.commit()


def query_one(*, info: MySqlConnInfo, query: str, params: Iterable | None = None):
    with connect(info) as conn:
        with conn.cursor() as cur:
            cur.execute(query, params or ())
            return cur.fetchone()


def query_all(*, info: MySqlConnInfo, query: str, params: Iterable | None = None):
    with connect(info) as conn:
        with conn.cursor() as cur:
            cur.execute(query, params or ())
            return cur.fetchall()

