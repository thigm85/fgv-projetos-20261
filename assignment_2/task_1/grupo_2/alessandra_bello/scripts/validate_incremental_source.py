#!/usr/bin/env python3
"""
validate_incremental_source.py
-------------------------------
Valida que a origem incremental está corretamente configurada e pronta
para o job Glue da Task 2.

Verificações:
  1. Tabela etl_watermark existe e contém o registro 'classicmodels_sales'.
  2. last_processed_order_date não é NULL.
  3. MAX(orders.orderDate) > last_processed_order_date  (dados pendentes de ETL).
  4. Integridade: pedidos com orderDate > watermark possuem linhas em orderdetails.

Exit codes:
  0  — todas as checagens passaram
  1  — uma ou mais checagens falharam

Uso:
    python scripts/validate_incremental_source.py

Variáveis de ambiente (ver .env.example):
    DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME
"""

import logging
import os
import sys

import pymysql
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

DB_CONFIG = {
    "host":        os.getenv("DB_HOST", "localhost"),
    "port":        int(os.getenv("DB_PORT", 3306)),
    "user":        os.getenv("DB_USER", "root"),
    "password":    os.getenv("DB_PASSWORD", ""),
    "database":    os.getenv("DB_NAME", "classicmodels"),
    "charset":     "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor,
    "autocommit":  True,
}

PIPELINE_NAME = "classicmodels_sales"

def check_watermark_table_exists(cursor) -> tuple[bool, str]:
    """Check 1: tabela etl_watermark existe."""
    cursor.execute(
        """
        SELECT COUNT(*) AS cnt
        FROM information_schema.tables
        WHERE table_schema = DATABASE()
          AND table_name = 'etl_watermark';
        """
    )
    exists = cursor.fetchone()["cnt"] > 0
    if exists:
        return True, "[CHECK 1] Tabela etl_watermark existe."
    return False, "[CHECK 1] Tabela etl_watermark NÃO existe. Execute init_watermark.py."

def check_pipeline_record_exists(cursor) -> tuple[bool, str]:
    """Check 2: registro 'classicmodels_sales' presente e last_processed_order_date não NULL."""
    cursor.execute(
        """
        SELECT pipeline_name, last_processed_order_date, last_run_status
        FROM etl_watermark
        WHERE pipeline_name = %(name)s;
        """,
        {"name": PIPELINE_NAME},
    )
    row = cursor.fetchone()
    if row is None:
        return (
            False,
            f"[CHECK 2] Registro '{PIPELINE_NAME}' não encontrado em etl_watermark.",
        )
    if row["last_processed_order_date"] is None:
        return (
            False,
            f"[CHECK 2] last_processed_order_date é NULL para '{PIPELINE_NAME}'.",
        )
    return (
        True,
        f"[CHECK 2] Registro encontrado | last_processed_order_date="
        f"{row['last_processed_order_date']} | status={row['last_run_status']}",
    )

def check_pending_orders(cursor) -> tuple[bool, str]:
    """Check 3: MAX(orders.orderDate) > last_processed_order_date."""
    cursor.execute(
        """
        SELECT
            MAX(o.orderDate)                AS max_order_date,
            w.last_processed_order_date     AS watermark_date
        FROM orders o
        CROSS JOIN etl_watermark w
        WHERE w.pipeline_name = %(name)s;
        """,
        {"name": PIPELINE_NAME},
    )
    row = cursor.fetchone()
    if row is None or row["max_order_date"] is None or row["watermark_date"] is None:
        return False, "[CHECK 3] Não foi possível comparar datas (dados ausentes)."

    max_date = row["max_order_date"]
    wm_date  = row["watermark_date"]

    if max_date > wm_date:
        return (
            True,
            f"[CHECK 3] Há dados pendentes de ETL: "
            f"MAX(orderDate)={max_date} > watermark={wm_date}",
        )
    return (
        False,
        f"[CHECK 3] Sem dados novos pendentes: "
        f"MAX(orderDate)={max_date} <= watermark={wm_date}. "
        f"Execute simulate_new_orders.py primeiro.",
    )

def check_orderdetails_integrity(cursor) -> tuple[bool, str]:
    """
    Check 4: pedidos com orderDate > watermark possuem linhas em orderdetails.
    Retorna falso se existir algum pedido novo sem detalhes.
    """
    cursor.execute(
        """
        SELECT COUNT(*) AS orphan_count
        FROM orders o
        JOIN etl_watermark w ON w.pipeline_name = %(name)s
        LEFT JOIN orderdetails od ON od.orderNumber = o.orderNumber
        WHERE o.orderDate > w.last_processed_order_date
          AND od.orderNumber IS NULL;
        """,
        {"name": PIPELINE_NAME},
    )
    orphans = cursor.fetchone()["orphan_count"]
    if orphans == 0:
        return (
            True,
            "[CHECK 4] Todos os pedidos novos possuem linhas em orderdetails.",
        )
    return (
        False,
        f"[CHECK 4] {orphans} pedido(s) novo(s) sem linhas em orderdetails (integridade quebrada).",
    )

CHECKS = [
    check_watermark_table_exists,
    check_pipeline_record_exists,
    check_pending_orders,
    check_orderdetails_integrity,
]

def run_checks(cursor) -> bool:
    all_passed = True
    print("\n" + "=" * 65)
    print("VALIDAÇÃO DA ORIGEM INCREMENTAL — classicmodels_sales")
    print("=" * 65)

    for i, check_fn in enumerate(CHECKS, start=1):
        try:
            passed, message = check_fn(cursor)
        except Exception as exc:
            passed = False
            message = f"[CHECK {i}] Exceção durante verificação: {exc}"

        print(message)
        log.info(message)

        if not passed:
            all_passed = False

    print("=" * 65)
    if all_passed:
        print("TODAS AS CHECAGENS PASSARAM — origem pronta para ETL.")
    else:
        print("UMA OU MAIS CHECAGENS FALHARAM — corrija antes de prosseguir.")
    print("=" * 65 + "\n")

    return all_passed

def main():
    log.info("=== validate_incremental_source.py iniciado ===")
    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cur:
            success = run_checks(cur)
        sys.exit(0 if success else 1)
    except Exception as exc:
        log.error(f"Erro fatal: {exc}")
        sys.exit(1)
    finally:
        conn.close()

if __name__ == "__main__":
    main()