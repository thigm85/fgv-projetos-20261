from __future__ import annotations

import argparse
import random
import sys
from datetime import date, timedelta
from decimal import Decimal

from common import PIPELINE_NAME, SOLUTION_LABEL, connect, fetch_one_value


def next_business_day(value: date) -> date:
    candidate = value + timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate += timedelta(days=1)
    return candidate


def get_baseline_date(cursor) -> date:
    watermark = fetch_one_value(
        cursor,
        "SELECT last_processed_order_date FROM etl_watermark WHERE pipeline_name = %s",
        (PIPELINE_NAME,),
    )
    max_order_date = fetch_one_value(cursor, "SELECT MAX(orderDate) FROM orders")
    candidates = [value for value in (watermark, max_order_date) if value is not None]
    if not candidates:
        raise RuntimeError("Não foi possível calcular a data base dos pedidos.")
    return max(candidates)


def get_next_order_number(cursor) -> int:
    current_max = fetch_one_value(cursor, "SELECT MAX(orderNumber) FROM orders")
    if current_max is None:
        return 1
    return int(current_max) + 1


def load_reference_data(cursor) -> tuple[list[int], list[dict]]:
    cursor.execute("SELECT customerNumber FROM customers")
    customers = [int(row["customerNumber"]) for row in cursor.fetchall()]

    cursor.execute("SELECT productCode, MSRP, buyPrice FROM products")
    products = cursor.fetchall()

    if not customers:
        raise RuntimeError("Tabela customers está vazia.")
    if not products:
        raise RuntimeError("Tabela products está vazia.")

    return customers, products


def simulate_new_orders(count: int, seed: int | None) -> dict:
    if count <= 0:
        raise ValueError("--count deve ser maior que zero.")

    rng = random.Random(seed)

    with connect() as connection:
        try:
            with connection.cursor() as cursor:
                customers, products = load_reference_data(cursor)
                order_number = get_next_order_number(cursor)
                order_date = get_baseline_date(cursor)

                created_order_numbers: list[int] = []
                created_dates: list[date] = []
                details_count = 0

                for index in range(count):
                    current_order_number = order_number + index
                    order_date = next_business_day(order_date)
                    required_date = order_date + timedelta(days=7)
                    customer_number = rng.choice(customers)

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
                        VALUES (%s, %s, %s, NULL, 'In Process', %s, %s)
                        """,
                        (
                            current_order_number,
                            order_date,
                            required_date,
                            f"Pedido simulado para origem incremental ({SOLUTION_LABEL})",
                            customer_number,
                        ),
                    )

                    line_count = rng.randint(1, min(3, len(products)))
                    selected_products = rng.sample(products, line_count)

                    for line_number, product in enumerate(selected_products, start=1):
                        reference_price = product["MSRP"] or product["buyPrice"] or Decimal("1.00")
                        price_each = Decimal(str(reference_price)).quantize(Decimal("0.01"))
                        quantity = rng.randint(1, 20)

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
                            (
                                current_order_number,
                                product["productCode"],
                                quantity,
                                price_each,
                                line_number,
                            ),
                        )
                        details_count += 1

                    created_order_numbers.append(current_order_number)
                    created_dates.append(order_date)

            connection.commit()
        except Exception:
            connection.rollback()
            raise

    return {
        "order_numbers": created_order_numbers,
        "start_date": min(created_dates),
        "end_date": max(created_dates),
        "details_count": details_count,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Simula novos pedidos incrementais no classicmodels.")
    parser.add_argument("--count", type=int, default=3, help="Número de pedidos a criar.")
    parser.add_argument("--seed", type=int, default=None, help="Seed opcional para reprodutibilidade.")
    args = parser.parse_args()

    try:
        summary = simulate_new_orders(args.count, args.seed)
    except Exception as exc:
        print(f"Erro ao simular pedidos: {exc}", file=sys.stderr)
        return 1

    order_numbers = summary["order_numbers"]
    print("Simulação individual concluída.")
    print(f"Pedidos criados: {order_numbers}")
    print(f"Faixa de datas: {summary['start_date']} até {summary['end_date']}")
    print(f"Linhas criadas em orderdetails: {summary['details_count']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
