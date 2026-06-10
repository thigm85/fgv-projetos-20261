"""Utilitários de conexão MySQL."""

from __future__ import annotations

from datetime import date, datetime

import mysql.connector
from mysql.connector import MySQLConnection

from config import db_config


def as_date(value: date | datetime | str | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def connect() -> MySQLConnection:
    cfg = db_config()
    return mysql.connector.connect(
        host=cfg["host"],
        port=cfg["port"],
        database=cfg["database"],
        user=cfg["user"],
        password=cfg["password"],
        autocommit=False,
    )
