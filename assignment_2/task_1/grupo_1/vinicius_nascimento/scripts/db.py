import os
import mysql.connector


def get_connection():
    return mysql.connector.connect(
        host=os.environ["DB_HOST"],
        port=int(os.environ.get("DB_PORT", "3306")),
        database=os.environ.get("DB_NAME", "classicmodels"),
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
    )