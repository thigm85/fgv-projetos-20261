"""
Valida que a origem incremental está pronta para o ETL.

Checks:
  1. etl_watermark existe e contém 'classicmodels_sales'.
  2. last_processed_order_date não é NULL.
  3. MAX(orders.orderDate) > last_processed_order_date (há dados pendentes).
  4. Todo orderNumber em orders tem ao menos uma linha em orderdetails.

Exit code: 0 = todas as checagens passaram, 1 = qualquer falha.
"""

import json
import logging
import os
import sys
from pathlib import Path

import boto3
import mysql.connector

sys.path.insert(0, str(Path(__file__).resolve().parent))
import envlocal

envlocal.load()

SECRET_ARN = os.environ["SECRET_ARN"]
REGION = os.environ.get("AWS_REGION", "us-east-1")
DB_NAME = "classicmodels"
PIPELINE_NAME = "classicmodels_sales"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("validate_incremental_source")

failures: list[str] = []


def ok(msg: str) -> None:
    log.info("  [ok]   %s", msg)


def fail(msg: str) -> None:
    log.error("  [FAIL] %s", msg)
    failures.append(msg)


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
    )


def check_watermark_table(cur) -> None:
    log.info("=== 1. etl_watermark existe e contém o registro ===")
    cur.execute(
        "SELECT COUNT(*) FROM information_schema.tables "
        "WHERE table_schema = %s AND table_name = 'etl_watermark'",
        (DB_NAME,),
    )
    if cur.fetchone()[0] == 0:
        fail("etl_watermark: tabela não existe — execute init_watermark.py primeiro")
        return False

    cur.execute(
        "SELECT last_processed_order_date, last_run_status "
        "FROM etl_watermark WHERE pipeline_name = %s",
        (PIPELINE_NAME,),
    )
    row = cur.fetchone()
    if row is None:
        fail(f"etl_watermark: registro '{PIPELINE_NAME}' ausente")
        return False

    ok(f"etl_watermark encontrada: watermark={row[0]} status={row[1]}")
    return True


def check_watermark_not_null(cur) -> None:
    log.info("=== 2. last_processed_order_date não é NULL ===")
    cur.execute(
        "SELECT last_processed_order_date FROM etl_watermark WHERE pipeline_name = %s",
        (PIPELINE_NAME,),
    )
    wm = cur.fetchone()[0]
    if wm is None:
        fail("last_processed_order_date é NULL — execute init_watermark.py")
    else:
        ok(f"last_processed_order_date = {wm}")
    return wm


def check_pending_orders(cur, watermark) -> None:
    log.info("=== 3. Há pedidos novos pendentes de ETL ===")
    cur.execute("SELECT MAX(orderDate) FROM orders")
    max_date = cur.fetchone()[0]
    if max_date is None:
        fail("orders: tabela vazia")
        return
    if max_date > watermark:
        ok(f"MAX(orderDate)={max_date} > watermark={watermark} — {(max_date - watermark).days} dia(s) pendente(s)")
    else:
        fail(f"MAX(orderDate)={max_date} não é > watermark={watermark} — sem dados novos")


def check_orderdetails_integrity(cur) -> None:
    log.info("=== 4. Integridade: pedidos com orderdetails ===")
    cur.execute(
        """
        SELECT COUNT(*)
        FROM orders o
        LEFT JOIN orderdetails od ON o.orderNumber = od.orderNumber
        WHERE od.orderNumber IS NULL
        """
    )
    orphans = cur.fetchone()[0]
    if orphans == 0:
        ok("Todos os pedidos possuem ao menos uma linha em orderdetails")
    else:
        fail(f"{orphans} pedido(s) sem linhas em orderdetails")


def main() -> int:
    conn = None
    try:
        secret = get_secret()
        conn = connect(secret)
        cur = conn.cursor()

        table_ok = check_watermark_table(cur)
        if not table_ok:
            return 1

        watermark = check_watermark_not_null(cur)
        if watermark is not None:
            check_pending_orders(cur, watermark)

        check_orderdetails_integrity(cur)

        cur.close()

    except Exception as exc:
        log.exception("Erro durante validação: %s", exc)
        return 1
    finally:
        if conn is not None and conn.is_connected():
            conn.close()

    log.info("=" * 50)
    log.info("RESULTADO: %d falha(s)", len(failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
