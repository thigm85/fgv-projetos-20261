"""
Helper para test_validate_catches_bad_data.sh.

Modos:
  inject   — INSERT em orders com orderNumber=9999999 SEM linha em orderdetails
  cleanup  — DELETE orderNumber=9999999

Bypassa a Lambda (escreve direto no RDS via mysql.connector).
"""

import json
import os
import sys
from pathlib import Path

import boto3
import mysql.connector

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import envlocal

envlocal.load()

SECRET_ARN = os.environ["SECRET_ARN"]
REGION = os.environ.get("AWS_REGION", "us-east-1")
DB_NAME = "classicmodels"

BAD_ORDER_NUMBER = 9999999


def get_secret() -> dict:
    client = boto3.client("secretsmanager", region_name=REGION)
    return json.loads(client.get_secret_value(SecretId=SECRET_ARN)["SecretString"])


def connect(secret: dict):
    return mysql.connector.connect(
        host=secret["host"],
        user=secret["username"],
        password=secret["password"],
        port=int(secret["port"]),
        database=DB_NAME,
        use_pure=True,
        connection_timeout=10,
        autocommit=False,
    )


def inject(conn) -> None:
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO orders
            (orderNumber, orderDate, requiredDate, shippedDate, status, comments, customerNumber)
        VALUES (%s, '2099-12-31', '2099-12-31', NULL, 'In Process', 'BAD DATA — orphan test', 103)
        """,
        (BAD_ORDER_NUMBER,),
    )
    conn.commit()
    cur.close()
    print(f"  Injetado orderNumber={BAD_ORDER_NUMBER} em orders SEM orderdetails")


def cleanup(conn) -> None:
    cur = conn.cursor()
    cur.execute("DELETE FROM orderdetails WHERE orderNumber = %s", (BAD_ORDER_NUMBER,))
    cur.execute("DELETE FROM orders WHERE orderNumber = %s", (BAD_ORDER_NUMBER,))
    conn.commit()
    cur.close()
    print(f"  Removido orderNumber={BAD_ORDER_NUMBER}")


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in ("inject", "cleanup"):
        print("uso: _inject_bad_order.py [inject|cleanup]")
        return 2

    mode = sys.argv[1]
    conn = None
    try:
        secret = get_secret()
        conn = connect(secret)
        if mode == "inject":
            inject(conn)
        else:
            cleanup(conn)
        return 0
    except Exception as exc:
        print(f"FALHA: {exc}")
        if conn is not None:
            conn.rollback()
        return 1
    finally:
        if conn is not None and conn.is_connected():
            conn.close()


if __name__ == "__main__":
    sys.exit(main())
