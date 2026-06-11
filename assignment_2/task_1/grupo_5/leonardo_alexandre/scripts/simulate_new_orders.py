"""
Insere pedidos simulados em orders + orderdetails para testar carga incremental.
Não atualiza etl_watermark (responsabilidade do Glue na Task 2).
"""

from __future__ import annotations

import argparse
import random
import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config import PIPELINE_NAME
from db import as_date, connect


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Simula novos pedidos no classicmodels.")
    parser.add_argument("--count", type=int, default=5, help="Número de pedidos a criar (default: 5)")
    parser.add_argument("--seed", type=int, default=None, help="Seed para reprodutibilidade")
    return parser.parse_args()


def next_business_dates(start: date, count: int) -> list[date]:
    dates: list[date] = []
    current = start
    while len(dates) < count:
        if current.weekday() < 5:
            dates.append(current)
        current += timedelta(days=1)
    return dates


def fetch_baseline(cursor) -> tuple[date, int, date]:
    cursor.execute(
        "SELECT last_processed_order_date FROM etl_watermark WHERE pipeline_name = %s",
        (PIPELINE_NAME,),
    )
    row = cursor.fetchone()
    if not row or row[0] is None:
        raise RuntimeError(
            f"Watermark {PIPELINE_NAME!r} ausente ou NULL. Execute init_watermark.py primeiro."
        )
    watermark_date = as_date(row[0])
    if watermark_date is None:
        raise RuntimeError(f"Watermark {PIPELINE_NAME!r} com last_processed_order_date NULL.")

    cursor.execute("SELECT COALESCE(MAX(orderDate), %s) FROM orders", (watermark_date,))
    max_order_date = as_date(cursor.fetchone()[0])

    cursor.execute("SELECT COALESCE(MAX(orderNumber), 0) FROM orders")
    max_order_number = int(cursor.fetchone()[0])

    return watermark_date, max_order_number, max_order_date


def fetch_customers_and_products(cursor) -> tuple[list[int], list[tuple[str, Decimal]]]:
    cursor.execute("SELECT customerNumber FROM customers")
    customers = [int(row[0]) for row in cursor.fetchall()]
    if not customers:
        raise RuntimeError("Nenhum customerNumber encontrado em customers.")

    cursor.execute("SELECT productCode, buyPrice FROM products")
    products = [(row[0], Decimal(str(row[1]))) for row in cursor.fetchall()]
    if not products:
        raise RuntimeError("Nenhum productCode encontrado em products.")

    return customers, products


def plan_order_dates(watermark_date: date, max_order_date: date, count: int) -> list[date]:
    baseline = max(watermark_date, max_order_date)
    recent_start = max(baseline + timedelta(days=1), date.today() - timedelta(days=14))
    return next_business_dates(recent_start, count)


def main() -> int:
    args = parse_args()
    if args.count < 1:
        print("ERRO: --count deve ser >= 1")
        return 1

    rng = random.Random(args.seed)
    conn = connect()
    created: list[dict] = []

    try:
        cursor = conn.cursor()
        watermark_date, max_order_number, max_order_date = fetch_baseline(cursor)
        customers, products = fetch_customers_and_products(cursor)
        order_dates = plan_order_dates(watermark_date, max_order_date, args.count)

        for index, order_date in enumerate(order_dates):
            order_number = max_order_number + index + 1
            customer_number = rng.choice(customers)
            product_code, buy_price = rng.choice(products)
            quantity = rng.randint(1, 20)
            price_each = (buy_price * Decimal("2.5")).quantize(Decimal("0.01"))
            required_date = order_date + timedelta(days=7)

            cursor.execute(
                """
                INSERT INTO orders (
                    orderNumber, orderDate, requiredDate, shippedDate,
                    status, comments, customerNumber
                ) VALUES (%s, %s, %s, NULL, 'In Process', %s, %s)
                """,
                (
                    order_number,
                    order_date,
                    required_date,
                    "Pedido simulado (Assignment 2 Task 1)",
                    customer_number,
                ),
            )
            cursor.execute(
                """
                INSERT INTO orderdetails (
                    orderNumber, productCode, quantityOrdered, priceEach, orderLineNumber
                ) VALUES (%s, %s, %s, %s, %s)
                """,
                (order_number, product_code, quantity, price_each, 1),
            )

            created.append(
                {
                    "order_number": order_number,
                    "order_date": order_date,
                    "customer_number": customer_number,
                    "product_code": product_code,
                    "quantity": quantity,
                    "price_each": price_each,
                    "sales_amount": (Decimal(quantity) * price_each).quantize(Decimal("0.01")),
                }
            )

        conn.commit()

        min_date = min(item["order_date"] for item in created)
        max_date = max(item["order_date"] for item in created)
        detail_rows = len(created)

        print(f"OK: {len(created)} pedido(s) simulado(s)")
        print(f"    watermark atual (não alterado): {watermark_date}")
        print(f"    orderNumber(s): {[item['order_number'] for item in created]}")
        print(f"    faixa de orderDate: {min_date} .. {max_date}")
        print(f"    linhas em orderdetails: {detail_rows}")
        for item in created:
            print(
                f"    - pedido {item['order_number']}: "
                f"{item['order_date']} | qty={item['quantity']} "
                f"price={item['price_each']} sales={item['sales_amount']}"
            )
        return 0
    except Exception as exc:
        conn.rollback()
        print(f"ERRO: {exc}")
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
