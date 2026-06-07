import os
import sys

import pymysql

RDS_HOST = os.environ["RDS_HOST"]
RDS_PORT = int(os.environ.get("RDS_PORT", 3306))
RDS_USER = os.environ["RDS_USER"]
RDS_PASSWORD = os.environ["RDS_PASSWORD"]
RDS_DB = os.environ.get("RDS_DB", "classicmodels")


def check(condition: bool, message: str):
    status = "OK" if condition else "FAIL"
    print(f"  [{status}] {message}")
    return condition


def main():
    conn = pymysql.connect(
        host=RDS_HOST,
        port=RDS_PORT,
        user=RDS_USER,
        password=RDS_PASSWORD,
        database=RDS_DB,
        autocommit=True,
        charset="utf8mb4",
    )

    failures = 0

    with conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = %s AND table_name = 'etl_watermark'",
            (RDS_DB,),
        )
        table_exists = cur.fetchone()[0] == 1

        print("\n--- Validação: Watermark ---")
        if not check(table_exists, "Tabela etl_watermark existe"):
            conn.close()
            print("\nValidação FALHOU (tabela ausente). Execute init_watermark.py primeiro.")
            sys.exit(1)

        cur.execute(
            "SELECT last_processed_order_date, last_run_status FROM etl_watermark WHERE pipeline_name = 'classicmodels_sales'"
        )
        row = cur.fetchone()

        record_exists = row is not None
        if not check(record_exists, "Registro 'classicmodels_sales' presente"):
            failures += 1
        else:
            watermark_date = row[0]
            failures += 0 if check(
                watermark_date is not None,
                f"last_processed_order_date não é NULL: {watermark_date}",
            ) else 1

            cur.execute("SELECT MAX(orderDate) FROM orders")
            max_order_date = cur.fetchone()[0]

            if max_order_date is not None and max_order_date > watermark_date:
                failures += 0 if check(
                    True,
                    f"MAX(orderDate)={max_order_date} > watermark={watermark_date} (dados pendentes detectados)",
                ) else 1
            elif max_order_date == watermark_date:
                failures += 0 if check(
                    True,
                    f"MAX(orderDate)={max_order_date} == watermark={watermark_date} (baseline coerente, sem dados pendentes)",
                ) else 1
            else:
                failures += 0 if check(
                    False,
                    f"MAX(orderDate)={max_order_date} < watermark={watermark_date} (baseline inconsistente)",
                ) else 1

        print("\n--- Validação: Integridade ---")
        cur.execute(
            """
            SELECT COUNT(*) FROM orders o
            WHERE NOT EXISTS (
                SELECT 1 FROM orderdetails od WHERE od.orderNumber = o.orderNumber
            )
            """
        )
        orphan_orders = cur.fetchone()[0]
        failures += 0 if check(
            orphan_orders == 0,
            f"Pedidos sem linhas em orderdetails: {orphan_orders}",
        ) else 1

    conn.close()

    print()
    if failures == 0:
        print("Validação PASSOU. Origem pronta para ETL incremental.")
        sys.exit(0)
    else:
        print(f"Validação FALHOU com {failures} erro(s).")
        sys.exit(1)


if __name__ == "__main__":
    main()
