"""
Valida se a origem incremental está pronta para o ETL da Task 2.
Exit code 0 apenas se todas as checagens passarem.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config import PIPELINE_NAME
from db import as_date, connect


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Valida etl_watermark e pedidos pendentes.")
    parser.add_argument(
        "--require-pending",
        action="store_true",
        help="Exige MAX(orderDate) > watermark (após simulate_new_orders)",
    )
    parser.add_argument(
        "--require-no-pending",
        action="store_true",
        help="Exige MAX(orderDate) == watermark (após init_watermark, antes da simulação)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.require_pending and args.require_no_pending:
        print("ERRO: use apenas um de --require-pending ou --require-no-pending")
        return 1

    failures: list[str] = []
    conn = connect()

    try:
        cursor = conn.cursor()

        cursor.execute("SHOW TABLES LIKE 'etl_watermark'")
        if not cursor.fetchone():
            failures.append("tabela etl_watermark não existe")

        watermark_date = None
        if not failures:
            cursor.execute(
                """
                SELECT last_processed_order_date, last_run_status
                FROM etl_watermark
                WHERE pipeline_name = %s
                """,
                (PIPELINE_NAME,),
            )
            row = cursor.fetchone()
            if not row:
                failures.append(f"registro {PIPELINE_NAME!r} ausente em etl_watermark")
            else:
                watermark_date, run_status = as_date(row[0]), row[1]
                if watermark_date is None:
                    failures.append("last_processed_order_date está NULL")
                else:
                    print(f"OK: watermark {PIPELINE_NAME!r} encontrado")
                    print(f"    last_processed_order_date = {watermark_date}")
                    print(f"    last_run_status = {run_status}")

        max_order_date = None
        if not failures:
            cursor.execute("SELECT MAX(orderDate) FROM orders")
            max_order_date = as_date(cursor.fetchone()[0])
            if max_order_date is None:
                failures.append("tabela orders vazia (MAX(orderDate) é NULL)")
            elif watermark_date is not None:
                if max_order_date < watermark_date:
                    failures.append(
                        f"MAX(orderDate)={max_order_date} é anterior ao watermark={watermark_date}"
                    )
                elif max_order_date == watermark_date:
                    print("OK: baseline coerente (sem pedidos pendentes de ETL)")
                else:
                    print(
                        f"OK: há dados pendentes de ETL "
                        f"(MAX(orderDate)={max_order_date} > watermark={watermark_date})"
                    )

                if args.require_pending and max_order_date <= watermark_date:
                    failures.append("esperava pedidos pendentes, mas MAX(orderDate) <= watermark")
                if args.require_no_pending and max_order_date != watermark_date:
                    failures.append("esperava ausência de pendências, mas MAX(orderDate) != watermark")

        if not failures and watermark_date is not None:
            cursor.execute(
                """
                SELECT o.orderNumber
                FROM orders o
                LEFT JOIN orderdetails od ON od.orderNumber = o.orderNumber
                WHERE o.orderDate > %s
                GROUP BY o.orderNumber
                HAVING COUNT(od.productCode) = 0
                """,
                (watermark_date,),
            )
            orphans = [row[0] for row in cursor.fetchall()]
            if orphans:
                failures.append(
                    f"pedidos sem orderdetails após watermark: {orphans}"
                )
            else:
                cursor.execute(
                    "SELECT COUNT(*) FROM orders WHERE orderDate > %s",
                    (watermark_date,),
                )
                pending_count = cursor.fetchone()[0]
                print(f"OK: integridade orderdetails (pendentes com linhas: {pending_count})")

        if failures:
            print("\nFALHA na validação:")
            for item in failures:
                print(f"  - {item}")
            return 1

        print("\nValidação concluída com sucesso.")
        return 0
    except Exception as exc:
        print(f"ERRO: {exc}")
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
