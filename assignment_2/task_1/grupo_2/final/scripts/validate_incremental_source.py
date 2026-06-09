#!/usr/bin/env python3
"""
Valida que a origem incremental está pronta para o ETL (Task 2).

Checks:
  1. etl_watermark existe e contém o registro 'classicmodels_sales'.
  2. last_processed_order_date não é NULL após inicialização.
  3. MAX(orders.orderDate) > last_processed_order_date (há dados pendentes de ETL).
  4. Integridade: todo orderNumber em orders tem ao menos uma linha em orderdetails.
  5. Consistência: quantityOrdered > 0 e priceEach > 0 em todas as orderdetails.

Fontes de design:
  - 5 checks com logging detalhado: Matheus Carvalho
  - information_schema para check de tabela: Alessandra Bello / Gustavo Tironi
  - Contagem de pendentes e detalhamento: Matheus Carvalho

Exit code: 0 = todas as checagens passaram, 1 = qualquer falha.
"""

import logging
import sys
from pathlib import Path

# Adiciona o diretório pai ao path para importar db_config
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import db_config

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
    log.info("  ✓ [OK]   %s", msg)


def fail(msg: str) -> None:
    log.error("  ✗ [FAIL] %s", msg)
    failures.append(msg)


def info(msg: str) -> None:
    log.info("  ℹ [INFO] %s", msg)


# ── Check 1: Tabela etl_watermark existe e contém o registro ─────────────────

def check_watermark_exists(cur) -> bool:
    """Verifica se etl_watermark existe e contém classicmodels_sales."""
    log.info("═══ Check 1: etl_watermark existe e contém o registro ═══")

    # Verifica se a tabela existe (via information_schema — Alessandra/Gustavo)
    cur.execute(
        "SELECT COUNT(*) FROM information_schema.tables "
        "WHERE table_schema = %s AND table_name = 'etl_watermark'",
        (DB_NAME,),
    )
    if cur.fetchone()[0] == 0:
        fail("Tabela etl_watermark NÃO existe — execute init_watermark.py primeiro.")
        return False

    # Verifica se o registro existe
    cur.execute(
        "SELECT last_processed_order_date, last_run_at, last_run_status "
        "FROM etl_watermark WHERE pipeline_name = %s",
        (PIPELINE_NAME,),
    )
    row = cur.fetchone()
    if row is None:
        fail(f"Registro '{PIPELINE_NAME}' NÃO encontrado na etl_watermark.")
        return False

    wm_date, run_at, status = row
    ok(f"etl_watermark encontrada: watermark={wm_date}, status={status}, last_run={run_at}")
    return True


# ── Check 2: last_processed_order_date não é NULL ─────────────────────────────

def check_watermark_not_null(cur):
    """Verifica se last_processed_order_date tem valor."""
    log.info("═══ Check 2: last_processed_order_date não é NULL ═══")

    cur.execute(
        "SELECT last_processed_order_date FROM etl_watermark WHERE pipeline_name = %s",
        (PIPELINE_NAME,),
    )
    wm = cur.fetchone()[0]

    if wm is None:
        fail("last_processed_order_date é NULL — execute init_watermark.py para inicializar.")
        return None

    ok(f"last_processed_order_date = {wm}")
    return wm


# ── Check 3: Há pedidos novos pendentes de ETL ───────────────────────────────

def check_pending_orders(cur, watermark) -> None:
    """Verifica se MAX(orderDate) > watermark (dados pendentes de ETL)."""
    log.info("═══ Check 3: Há pedidos novos pendentes de ETL ═══")

    cur.execute("SELECT MAX(orderDate) FROM orders")
    max_date = cur.fetchone()[0]

    if max_date is None:
        fail("Tabela 'orders' está vazia.")
        return

    if max_date > watermark:
        pending_days = (max_date - watermark).days
        cur.execute(
            "SELECT COUNT(*) FROM orders WHERE orderDate > %s",
            (watermark,),
        )
        pending_count = cur.fetchone()[0]
        ok(
            f"MAX(orderDate)={max_date} > watermark={watermark} — "
            f"{pending_count} pedido(s) pendente(s) ({pending_days} dia(s))"
        )
    else:
        # Não é uma falha — é um estado válido: tudo já foi processado
        info(
            f"MAX(orderDate)={max_date} ≤ watermark={watermark} — "
            f"sem dados novos pendentes de ETL (estado limpo)."
        )


# ── Check 4: Todo pedido tem ao menos uma linha em orderdetails ──────────────

def check_orderdetails_integrity(cur) -> None:
    """Verifica que não existem pedidos sem linhas em orderdetails."""
    log.info("═══ Check 4: Integridade orders ↔ orderdetails ═══")

    cur.execute(
        """
        SELECT o.orderNumber
        FROM orders o
        LEFT JOIN orderdetails od ON o.orderNumber = od.orderNumber
        WHERE od.orderNumber IS NULL
        """
    )
    orphans = cur.fetchall()

    if not orphans:
        ok("Todos os pedidos possuem ao menos uma linha em orderdetails.")
    else:
        orphan_ids = [row[0] for row in orphans]
        fail(
            f"{len(orphan_ids)} pedido(s) sem linhas em orderdetails: "
            f"{orphan_ids[:10]}{'...' if len(orphan_ids) > 10 else ''}"
        )


# ── Check 5: Consistência de valores em orderdetails ─────────────────────────

def check_orderdetails_values(cur) -> None:
    """Verifica que quantityOrdered > 0 e priceEach > 0 em todas as linhas."""
    log.info("═══ Check 5: Consistência de valores em orderdetails ═══")

    # quantityOrdered <= 0
    cur.execute("SELECT COUNT(*) FROM orderdetails WHERE quantityOrdered <= 0")
    bad_qty = cur.fetchone()[0]

    # priceEach <= 0
    cur.execute("SELECT COUNT(*) FROM orderdetails WHERE priceEach <= 0")
    bad_price = cur.fetchone()[0]

    if bad_qty == 0 and bad_price == 0:
        ok("Todos os valores em orderdetails são positivos (qty > 0, price > 0).")
    else:
        if bad_qty > 0:
            fail(f"{bad_qty} linha(s) com quantityOrdered ≤ 0.")
        if bad_price > 0:
            fail(f"{bad_price} linha(s) com priceEach ≤ 0.")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    conn = None
    try:
        conn = db_config.get_connection(autocommit=True)
        cur = conn.cursor()

        # Check 1
        table_ok = check_watermark_exists(cur)
        if not table_ok:
            log.info("")
            log.info("═" * 60)
            log.error("RESULTADO: FALHOU — etl_watermark não está configurada.")
            return 1

        # Check 2
        watermark = check_watermark_not_null(cur)

        # Check 3 (depende do check 2)
        if watermark is not None:
            check_pending_orders(cur, watermark)

        # Check 4
        check_orderdetails_integrity(cur)

        # Check 5
        check_orderdetails_values(cur)

        cur.close()

    except Exception as exc:
        log.exception("Erro durante validação: %s", exc)
        return 1
    finally:
        if conn is not None:
            conn.close()

    # Resultado final
    log.info("")
    log.info("═" * 60)
    total_checks = 5
    n_failures = len(failures)
    passed = total_checks - n_failures

    if n_failures == 0:
        log.info("RESULTADO: %d/%d checks passaram ✓", passed, total_checks)
        return 0
    else:
        log.error("RESULTADO: %d/%d checks passaram — %d falha(s):", passed, total_checks, n_failures)
        for f in failures:
            log.error("  • %s", f)
        return 1


if __name__ == "__main__":
    sys.exit(main())
