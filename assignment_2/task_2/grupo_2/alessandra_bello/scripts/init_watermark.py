#!/usr/bin/env python3
"""
init_watermark.py
-----------------
Cria a tabela etl_watermark no banco classicmodels (se não existir)
e insere/valida o registro inicial para o pipeline 'classicmodels_sales'.

Idempotente: pode ser executado múltiplas vezes com segurança.

Uso:
    python scripts/init_watermark.py

Variáveis de ambiente (ver .env.example):
    DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME
"""

import os
import sys
import logging
from datetime import datetime

import pymysql
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

DB_CONFIG = {
    "host":     os.getenv("DB_HOST", "localhost"),
    "port":     int(os.getenv("DB_PORT", 3306)),
    "user":     os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "classicmodels"),
    "charset":  "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor,
    "autocommit": False,
}

PIPELINE_NAME = "classicmodels_sales"

DDL_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS etl_watermark (
    pipeline_name             VARCHAR(64)  NOT NULL,
    last_processed_order_date DATE         NULL,
    last_run_at               DATETIME     NULL,
    last_run_status           VARCHAR(32)  NOT NULL DEFAULT 'NEVER_RUN',
    PRIMARY KEY (pipeline_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""

SQL_MAX_ORDER_DATE = "SELECT MAX(orderDate) AS max_date FROM orders;"

SQL_INSERT_INITIAL = """
INSERT INTO etl_watermark
    (pipeline_name, last_processed_order_date, last_run_at, last_run_status)
VALUES
    (%(pipeline_name)s, %(max_date)s, NULL, 'NEVER_RUN')
ON DUPLICATE KEY UPDATE
    -- Só atualiza last_processed_order_date se ainda estiver NULL
    -- (preserva progresso real de execuções anteriores)
    last_processed_order_date = CASE
        WHEN last_processed_order_date IS NULL THEN VALUES(last_processed_order_date)
        ELSE last_processed_order_date
    END;
"""

SQL_SELECT_WATERMARK = """
SELECT pipeline_name,
       last_processed_order_date,
       last_run_at,
       last_run_status
FROM etl_watermark
WHERE pipeline_name = %(pipeline_name)s;
"""

def get_connection():
    """Abre e retorna uma conexão PyMySQL."""
    return pymysql.connect(**DB_CONFIG)

def create_watermark_table(cursor):
    log.info("Verificando/criando tabela etl_watermark …")
    cursor.execute(DDL_CREATE_TABLE)
    log.info("Tabela etl_watermark OK.")

def get_max_order_date(cursor):
    cursor.execute(SQL_MAX_ORDER_DATE)
    row = cursor.fetchone()
    max_date = row["max_date"] if row else None
    if max_date is None:
        log.error("Tabela orders está vazia ou não existe. Verifique o banco.")
        sys.exit(1)
    log.info(f"MAX(orders.orderDate) encontrado: {max_date}")
    return max_date

def upsert_initial_record(cursor, max_date):
    log.info(f"Inserindo/validando registro inicial para pipeline '{PIPELINE_NAME}' …")
    cursor.execute(
        SQL_INSERT_INITIAL,
        {"pipeline_name": PIPELINE_NAME, "max_date": max_date},
    )
    affected = cursor.rowcount
    if affected == 1:
        log.info("Registro inicial inserido com sucesso.")
    elif affected == 2:
        log.info("Registro já existia; last_processed_order_date atualizado (estava NULL).")
    else:
        log.info("Registro já existia com last_processed_order_date preenchido — sem alteração.")

def print_watermark_state(cursor):
    cursor.execute(SQL_SELECT_WATERMARK, {"pipeline_name": PIPELINE_NAME})
    row = cursor.fetchone()
    if row:
        log.info("Estado atual do watermark:")
        for col, val in row.items():
            log.info(f"  {col}: {val}")
    else:
        log.warning("Registro de watermark não encontrado após upsert — verifique.")

def main():
    log.info("=== init_watermark.py iniciado ===")
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            create_watermark_table(cur)
            max_date = get_max_order_date(cur)
            upsert_initial_record(cur, max_date)
            conn.commit()
            print_watermark_state(cur)
        log.info("=== init_watermark.py concluído com sucesso ===")
    except Exception as exc:
        conn.rollback()
        log.error(f"Erro durante inicialização: {exc}")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
