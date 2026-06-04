import argparse
import sys

from db import connect


PIPELINE_NAME = "classicmodels_sales"


def as_date(value):
    return value.date() if hasattr(value, "date") else value


def parse_args():
    parser = argparse.ArgumentParser(description="Valida origem incremental do classicmodels.")
    parser.add_argument(
        "--require-pending",
        action="store_true",
        help="Falha se nao houver orders.orderDate maior que o watermark.",
    )
    return parser.parse_args()


def fail(errors, message):
    print(f"[ERRO] {message}")
    errors.append(message)


def main():
    args = parse_args()
    errors = []
    conn = connect()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SHOW TABLES LIKE 'etl_watermark'")
    if cursor.fetchone() is None:
        fail(errors, "Tabela etl_watermark nao existe.")
        cursor.close()
        conn.close()
        return 1

    cursor.execute(
        """
        SELECT pipeline_name, last_processed_order_date, last_run_at, last_run_status
        FROM etl_watermark
        WHERE pipeline_name = %s
        """,
        (PIPELINE_NAME,),
    )
    watermark = cursor.fetchone()
    if not watermark:
        fail(errors, "Registro classicmodels_sales ausente em etl_watermark.")
        cursor.close()
        conn.close()
        return 1

    if watermark["last_processed_order_date"] is None:
        fail(errors, "last_processed_order_date esta NULL.")

    cursor.execute("SELECT MAX(orderDate) AS max_order_date FROM orders")
    max_order_date = as_date(cursor.fetchone()["max_order_date"])
    if max_order_date is None:
        fail(errors, "Tabela orders nao possui registros.")

    pending_count = 0
    orphan_pending_orders = 0
    if watermark["last_processed_order_date"] is not None:
        cursor.execute(
            """
            SELECT COUNT(*) AS pending_count
            FROM orders
            WHERE orderDate > %s
            """,
            (watermark["last_processed_order_date"],),
        )
        pending_count = cursor.fetchone()["pending_count"]

        cursor.execute(
            """
            SELECT COUNT(*) AS orphan_pending_orders
            FROM orders o
            LEFT JOIN orderdetails od ON od.orderNumber = o.orderNumber
            WHERE o.orderDate > %s
              AND od.orderNumber IS NULL
            """,
            (watermark["last_processed_order_date"],),
        )
        orphan_pending_orders = cursor.fetchone()["orphan_pending_orders"]

    has_pending = (
        watermark["last_processed_order_date"] is not None
        and max_order_date is not None
        and max_order_date > as_date(watermark["last_processed_order_date"])
    )

    if args.require_pending and not has_pending:
        fail(errors, "Nao ha pedidos pendentes de ETL acima do watermark.")
    if orphan_pending_orders > 0:
        fail(errors, f"Pedidos pendentes sem orderdetails: {orphan_pending_orders}.")

    cursor.close()
    conn.close()

    print("Validacao da origem incremental:")
    print(f"- pipeline_name: {watermark['pipeline_name']}")
    print(f"- last_processed_order_date: {watermark['last_processed_order_date']}")
    print(f"- max_order_date: {max_order_date}")
    print(f"- pedidos_pendentes: {pending_count}")
    print(f"- pedidos_pendentes_sem_orderdetails: {orphan_pending_orders}")

    if errors:
        print("\nValidacao falhou.")
        return 1

    if has_pending:
        print("\nValidacao concluida com sucesso: ha dados novos pendentes de ETL.")
    else:
        print("\nValidacao concluida com sucesso: baseline coerente, sem dados pendentes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
