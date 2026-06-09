"""
Task 1 (3.3) — Valida que a origem está pronta para o ETL incremental da Task 2.

Checagens:
  1. Tabela etl_watermark existe e contém o registro 'classicmodels_sales'.
  2. last_processed_order_date não é NULL.
  3. Pendência de dados novos (modo conforme flag):
       - sem --require-pending (baseline/passo 2): passa se MAX(orderDate) >= watermark.
       - com --require-pending (pós-simulação/passo 4): exige MAX(orderDate) > watermark.
  4. Integridade: todo pedido com orderDate > watermark possui >= 1 linha em orderdetails.

Exit code 0 = todas passaram; 1 = qualquer falha (critério 3 da Task 1).

Uso:
  python validate_incremental_source.py                  # baseline (sem pendência exigida)
  python validate_incremental_source.py --require-pending # exige dados pendentes
"""
import argparse
import sys

from db import load_config, connect_with_retry

PIPELINE_NAME = "classicmodels_sales"
PASS = "[PASS]"
FAIL = "[FAIL]"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Valida a origem incremental (etl_watermark + orders).")
    p.add_argument(
        "--require-pending",
        action="store_true",
        help="Exige MAX(orderDate) > watermark (use após simular pedidos).",
    )
    return p.parse_args()


def check(condition: bool, msg: str, failures: list) -> None:
    print(f"  {PASS if condition else FAIL} {msg}")
    if not condition:
        failures.append(msg)


def scalar(cur, sql, params=None):
    cur.execute(sql, params or ())
    return cur.fetchone()[0]


def validate(conn, require_pending: bool) -> list:
    failures = []
    with conn.cursor() as cur:
        # 1. Tabela existe?
        print("\nCheck 1/4 — Tabela etl_watermark e registro")
        table_exists = scalar(
            cur,
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_schema = DATABASE() AND table_name = 'etl_watermark'",
        ) > 0
        check(table_exists, "Tabela 'etl_watermark' existe", failures)

        watermark = None
        if table_exists:
            cur.execute(
                "SELECT last_processed_order_date FROM etl_watermark WHERE pipeline_name = %s",
                (PIPELINE_NAME,),
            )
            row = cur.fetchone()
            check(row is not None, f"Registro '{PIPELINE_NAME}' presente", failures)
            if row is not None:
                watermark = row[0]
        else:
            failures.append("Tabela ausente — checagens seguintes ignoradas")
            return failures

        # 2. watermark não-nulo
        print("\nCheck 2/4 — Watermark inicializado")
        check(watermark is not None, f"last_processed_order_date não é NULL (={watermark})", failures)
        if watermark is None:
            return failures

        # 3. Pendência de dados novos
        print("\nCheck 3/4 — Pendência de dados novos")
        max_order_date = scalar(cur, "SELECT MAX(orderDate) FROM orders")
        if require_pending:
            check(
                max_order_date is not None and max_order_date > watermark,
                f"MAX(orderDate)={max_order_date} > watermark={watermark} (há dados pendentes)",
                failures,
            )
        else:
            check(
                max_order_date is not None and max_order_date >= watermark,
                f"MAX(orderDate)={max_order_date} >= watermark={watermark} (baseline coerente)",
                failures,
            )
            if max_order_date is not None and max_order_date > watermark:
                print(f"  (info) Há dados pendentes de ETL: {max_order_date} > {watermark}")

        # 4. Integridade: pedidos novos têm orderdetails
        print("\nCheck 4/4 — Integridade dos pedidos pendentes")
        pending_orders = scalar(
            cur, "SELECT COUNT(*) FROM orders WHERE orderDate > %s", (watermark,)
        )
        orphan_orders = scalar(
            cur,
            "SELECT COUNT(*) FROM orders o "
            "LEFT JOIN orderdetails od ON o.orderNumber = od.orderNumber "
            "WHERE o.orderDate > %s AND od.orderNumber IS NULL",
            (watermark,),
        )
        check(
            orphan_orders == 0,
            f"Pedidos pendentes sem orderdetails: {orphan_orders} "
            f"(de {pending_orders} pedido(s) com orderDate > watermark)",
            failures,
        )

    return failures


def main() -> int:
    args = parse_args()
    print("=" * 60)
    print("Task 1 (3.3) — Validação da origem incremental")
    print(f"  modo: {'require-pending' if args.require_pending else 'baseline'}")
    print("=" * 60)

    cfg = load_config()
    conn = None
    try:
        conn = connect_with_retry(cfg)
        failures = validate(conn, args.require_pending)
    finally:
        if conn:
            conn.close()
            print("\n  Conexão encerrada.")

    print("\n" + "=" * 60)
    if failures:
        print(f"REPROVADO — {len(failures)} checagem(ns) falharam:")
        for f in failures:
            print(f"  x {f}")
        print("=" * 60)
        return 1

    print("APROVADO — todas as checagens passaram.")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
