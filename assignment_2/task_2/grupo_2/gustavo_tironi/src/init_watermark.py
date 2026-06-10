"""
Inicializa a tabela etl_watermark no banco classicmodels.

Idempotente:
  - Cria a tabela se não existir.
  - Insere o registro 'classicmodels_sales' se ausente.
  - Inicializa last_processed_order_date com MAX(orders.orderDate).

Exit code: 0 = sucesso, 1 = falha.
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
log = logging.getLogger("init_watermark")

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS etl_watermark (
    pipeline_name           VARCHAR(64)  NOT NULL,
    last_processed_order_date DATE        NULL,
    last_run_at             DATETIME     NULL,
    last_run_status         VARCHAR(32)  NOT NULL DEFAULT 'NEVER_RUN',
    PRIMARY KEY (pipeline_name)
)
"""

INSERT_SQL = """
INSERT INTO etl_watermark (pipeline_name, last_processed_order_date, last_run_at, last_run_status)
SELECT %s, MAX(orderDate), NULL, 'NEVER_RUN'
FROM orders
WHERE NOT EXISTS (
    SELECT 1 FROM etl_watermark WHERE pipeline_name = %s
)
"""


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


def main() -> int:
    conn = None
    try:
        secret = get_secret()
        conn = connect(secret)
        cur = conn.cursor()

        log.info("Criando tabela etl_watermark (se não existir)...")
        cur.execute(CREATE_TABLE_SQL)

        log.info("Inserindo registro '%s' (se ausente)...", PIPELINE_NAME)
        cur.execute(INSERT_SQL, (PIPELINE_NAME, PIPELINE_NAME))
        inserted = cur.rowcount

        conn.commit()

        cur.execute(
            "SELECT pipeline_name, last_processed_order_date, last_run_status "
            "FROM etl_watermark WHERE pipeline_name = %s",
            (PIPELINE_NAME,),
        )
        row = cur.fetchone()
        cur.close()

        if inserted > 0:
            log.info("Registro criado: pipeline=%s watermark=%s status=%s", *row)
        else:
            log.info("Registro já existia: pipeline=%s watermark=%s status=%s", *row)

        return 0

    except Exception as exc:
        log.exception("Falha: %s", exc)
        if conn is not None:
            conn.rollback()
        return 1
    finally:
        if conn is not None and conn.is_connected():
            conn.close()


if __name__ == "__main__":
    sys.exit(main())
