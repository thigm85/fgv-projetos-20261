import os

import pymysql
from pymysql.cursors import DictCursor


def get_connection():
    host = os.getenv("DB_HOST")
    user = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD")
    database = os.getenv("DB_NAME", "classicmodels")
    port = int(os.getenv("DB_PORT", "3306"))

    missing = [name for name, value in (
        ("DB_HOST", host),
        ("DB_USER", user),
        ("DB_PASSWORD", password),
    ) if not value]
    if missing:
        raise SystemExit(
            "Missing environment variables: {}.\n"
            "Set DB_HOST, DB_USER, DB_PASSWORD and optionally DB_NAME, DB_PORT.".format(
                ", ".join(missing)
            )
        )

    return pymysql.connect(
        host=host,
        user=user,
        password=password,
        database=database,
        port=port,
        cursorclass=DictCursor,
        autocommit=False,
    )
