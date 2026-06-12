import argparse
import random
from datetime import timedelta
from decimal import Decimal

from db import connect


PIPELINE_NAME = "classicmodels_sales"


def as_date(value):
    return value.date() if hasattr(value, "date") else value


def parse_args():
    parser = argparse.ArgumentParser(description="Simula novos pedidos no classicmodels.")
    parser.add_argument("--count", type=int, default=5, help="Numero de pedidos a criar.")
    parser.add_argument("--seed", type=int, default=None, help="Seed opcional para reprodutibilidade.")
    return parser.parse_args()


def fetch_one(cursor, query, params=None):
    cursor.execute(query, params or ())
    return cursor.fetchone()


def main():
    args = parse_args()
    if args.count <= 0:
        raise ValueError("--count deve ser maior que zero.")

    rng = random.Random(args.seed)
    conn = connect()
    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute("START TRANSACTION")

        watermark_row = fetch_one(
            cursor,
            """
            SELECT last_processed_order_date
            FROM etl_watermark
            WHERE pipeline_name = %s
            FOR UPDATE
            """,
            (PIPELINE_NAME,),
        )
        if not watermark_row or watermark_row["last_processed_order_date"] is None:
            raise RuntimeError("Execute init_watermark.py antes de simular novos pedidos.")

        max_order_row = fetch_one(cursor, "SELECT MAX(orderDate) AS max_order_date FROM orders")
        watermark_date = as_date(watermark_row["last_processed_order_date"])
        max_order_date = as_date(max_order_row["max_order_date"])
        base_date = max(watermark_date, max_order_date)

        cursor.execute("SELECT customerNumber FROM customers ORDER BY customerNumber")
        customers = [row["customerNumber"] for row in cursor.fetchall()]
        cursor.execute(
            """
            SELECT productCode, COALESCE(MSRP, buyPrice) AS price
            FROM products
            WHERE COALESCE(MSRP, buyPrice) IS NOT NULL
            ORDER BY productCode
            """
        )
        products = cursor.fetchall()

        if not customers or not products:
            raise RuntimeError("Banco sem customers ou products suficientes para a simulacao.")

        next_order_number = fetch_one(cursor, "SELECT COALESCE(MAX(orderNumber), 0) + 1 AS next_id FROM orders")[
            "next_id"
        ]
        created_orders = []
        created_orderdetails = 0

        for index in range(args.count):
            order_number = next_order_number + index
            order_date = base_date + timedelta(days=index + 1)
            required_date = order_date + timedelta(days=7)
            customer_number = rng.choice(customers)
            product = rng.choice(products)
            quantity = rng.randint(1, 20)
            price_each = Decimal(str(product["price"])).quantize(Decimal("0.01"))

            cursor.execute(
                """
                INSERT INTO orders (
                    orderNumber,
                    orderDate,
                    requiredDate,
                    shippedDate,
                    status,
                    comments,
                    customerNumber
                )
                VALUES (%s, %s, %s, NULL, %s, %s, %s)
                """,
                (
                    order_number,
                    order_date,
                    required_date,
                    "In Process",
                    "Simulated incremental order for Assignment 2 Task 1",
                    customer_number,
                ),
            )
            cursor.execute(
                """
                INSERT INTO orderdetails (
                    orderNumber,
                    productCode,
                    quantityOrdered,
                    priceEach,
                    orderLineNumber
                )
                VALUES (%s, %s, %s, %s, %s)
                """,
                (order_number, product["productCode"], quantity, price_each, 1),
            )
            created_orders.append((order_number, order_date))
            created_orderdetails += 1

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()

    dates = [order_date for _, order_date in created_orders]
    print("Simulacao concluida.")
    print(f"- pedidos_criados: {[order_number for order_number, _ in created_orders]}")
    print(f"- data_inicial: {min(dates)}")
    print(f"- data_final: {max(dates)}")
    print(f"- linhas_orderdetails: {created_orderdetails}")
    print("- watermark_atualizado: nao")


if __name__ == "__main__":
    main()
