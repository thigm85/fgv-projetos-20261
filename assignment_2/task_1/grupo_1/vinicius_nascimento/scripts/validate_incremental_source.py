import sys

from db import get_connection


PIPELINE_NAME = "classicmodels_sales"


def table_exists(cursor):
    cursor.execute("SHOW TABLES LIKE 'etl_watermark'")
    return cursor.fetchone() is not None


def get_watermark(cursor):
    cursor.execute("""
        SELECT last_processed_order_date
        FROM etl_watermark
        WHERE pipeline_name = %s
    """, (PIPELINE_NAME,))
    row = cursor.fetchone()
    return row[0] if row else None


def get_max_order_date(cursor):
    cursor.execute("SELECT MAX(orderDate) FROM orders")
    return cursor.fetchone()[0]


def count_orphan_pending_orders(cursor):
    cursor.execute("""
        SELECT COUNT(*)
        FROM orders o
        LEFT JOIN orderdetails od
            ON o.orderNumber = od.orderNumber
        WHERE o.orderDate > (
            SELECT last_processed_order_date
            FROM etl_watermark
            WHERE pipeline_name = %s
        )
        AND od.orderNumber IS NULL
    """, (PIPELINE_NAME,))
    return cursor.fetchone()[0]


def count_pending_orders(cursor):
    cursor.execute("""
        SELECT COUNT(*)
        FROM orders
        WHERE orderDate > (
            SELECT last_processed_order_date
            FROM etl_watermark
            WHERE pipeline_name = %s
        )
    """, (PIPELINE_NAME,))
    return cursor.fetchone()[0]


def count_pending_orderdetails(cursor):
    cursor.execute("""
        SELECT COUNT(*)
        FROM orderdetails od
        INNER JOIN orders o
            ON od.orderNumber = o.orderNumber
        WHERE o.orderDate > (
            SELECT last_processed_order_date
            FROM etl_watermark
            WHERE pipeline_name = %s
        )
    """, (PIPELINE_NAME,))
    return cursor.fetchone()[0]


def main():
    errors = []

    conn = get_connection()
    cursor = conn.cursor()

    try:
        if not table_exists(cursor):
            errors.append("Tabela etl_watermark não existe.")
        else:
            watermark = get_watermark(cursor)

            if watermark is None:
                errors.append("Registro classicmodels_sales ausente ou last_processed_order_date NULL.")
            else:
                max_order_date = get_max_order_date(cursor)

                if max_order_date is None:
                    errors.append("Tabela orders está vazia.")
                elif max_order_date < watermark:
                    errors.append(
                        f"MAX(orderDate) menor que watermark. max_order_date={max_order_date}, watermark={watermark}"
                    )
                else:
                    pending_orders = count_pending_orders(cursor)
                    pending_details = count_pending_orderdetails(cursor)
                    orphan_pending_orders = count_orphan_pending_orders(cursor)

                    print(f"Watermark: {watermark}")
                    print(f"MAX(orderDate): {max_order_date}")
                    print(f"Pedidos pendentes de ETL: {pending_orders}")
                    print(f"Linhas pending em orderdetails: {pending_details}")

                    if max_order_date > watermark:
                        print("Status incremental: há dados novos pendentes.")
                    else:
                        print("Status incremental: baseline coerente, sem dados pendentes.")

                    if orphan_pending_orders > 0:
                        errors.append(
                            f"Existem {orphan_pending_orders} pedidos pendentes sem linhas em orderdetails."
                        )

                    if pending_orders > 0 and pending_details == 0:
                        errors.append(
                            "Há pedidos pendentes, mas nenhuma linha correspondente em orderdetails."
                        )

        if errors:
            print("\nVALIDATION FAILED")
            for error in errors:
                print(f"- {error}")
            sys.exit(1)

        print("\nVALIDATION PASSED")
        sys.exit(0)

    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    main()