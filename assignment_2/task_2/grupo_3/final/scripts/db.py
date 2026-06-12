import os
import sys

import mysql.connector

from env_loader import load_local_env


def connect():
    load_local_env()

    host = os.getenv("DB_HOST")
    user = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD")
    database = os.getenv("DB_NAME", "classicmodels")
    port = int(os.getenv("DB_PORT", "3306"))
    ssl_ca = os.getenv("DB_SSL_CA")

    missing = [
        name
        for name, value in {
            "DB_HOST": host,
            "DB_USER": user,
            "DB_PASSWORD": password,
        }.items()
        if not value
    ]
    if missing:
        print(f"[ERRO] Variaveis obrigatorias ausentes: {', '.join(missing)}")
        sys.exit(1)

    connection_args = {
        "host": host,
        "port": port,
        "user": user,
        "password": password,
        "database": database,
        "ssl_disabled": False,
    }
    if ssl_ca:
        connection_args["ssl_ca"] = ssl_ca

    return mysql.connector.connect(**connection_args)
