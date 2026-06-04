from __future__ import annotations

import argparse
import sys

from common import PIPELINE_NAME, connect


def validate(require_pending: bool) -> list[str]:
    errors: list[str] = []

    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT COUNT(*) AS total
                FROM information_schema.tables
                WHERE table_schema = DATABASE()
                  AND table_name = 'etl_watermark'
                """
            )
            if cursor.fetchone()["total"] != 1:
                return ["Tabela etl_watermark não existe."]

            cursor.execute(
                """
                SELECT last_processed_order_date, last_run_at, last_run_status
                FROM etl_watermark
                WHERE pipeline_name = %s
                """,
                (PIPELINE_NAME,),
            )
            watermark = cursor.fetchone()
            if watermark is None:
                return [f"Registro {PIPELINE_NAME} não existe em etl_watermark."]

            last_processed = watermark["last_processed_order_date"]
            if last_processed is None:
                errors.append("last_processed_order_date está NULL.")

            cursor.execute("SELECT MAX(orderDate) AS max_order_date FROM orders")
            max_order_date = cursor.fetchone()["max_order_date"]
            if max_order_date is None:
                errors.append("Tabela orders não possui pedidos.")
            elif last_processed is not None:
                if max_order_date < last_processed:
                    errors.append(
                        f"MAX(orderDate)={max_order_date} é menor que watermark={last_processed}."
                    )
                elif require_pending and max_order_date <= last_processed:
                    errors.append(
                        f"Não há pedidos pendentes: MAX(orderDate)={max_order_date}, watermark={last_processed}."
                    )

            cursor.execute(
                """
                SELECT COUNT(DISTINCT o.orderNumber) AS total
                FROM orders o
                LEFT JOIN orderdetails od ON od.orderNumber = o.orderNumber
                WHERE od.orderNumber IS NULL
                """
            )
            orphan_orders = cursor.fetchone()["total"]
            if orphan_orders:
                errors.append(f"Existem {orphan_orders} pedidos sem linhas em orderdetails.")

            if last_processed is not None:
                cursor.execute(
                    """
                    SELECT COUNT(DISTINCT o.orderNumber) AS total
                    FROM orders o
                    JOIN orderdetails od ON od.orderNumber = o.orderNumber
                    WHERE o.orderDate > %s
                    """,
                    (last_processed,),
                )
                pending_orders_with_details = cursor.fetchone()["total"]
                if require_pending and pending_orders_with_details == 0:
                    errors.append("Não há pedidos pendentes com linhas em orderdetails.")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Valida a origem incremental do classicmodels.")
    parser.add_argument(
        "--require-pending",
        action="store_true",
        help="Falha se MAX(orderDate) não for maior que o watermark.",
    )
    args = parser.parse_args()

    try:
        errors = validate(args.require_pending)
    except Exception as exc:
        print(f"Erro durante validação: {exc}", file=sys.stderr)
        return 1

    if errors:
        print("Validação falhou:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("Validação concluída com sucesso.")
    if args.require_pending:
        print("Há pedidos pendentes para o ETL incremental.")
    else:
        print("Watermark e integridade mínima estão consistentes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
