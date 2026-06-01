import argparse
import random
from datetime import datetime, date, timedelta

from db import get_connection


PIPELINE_NAME = "classicmodels_sales"


def normalize_date(value):
    if isinstance(value, date):
        return value

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, str):
        value = value.strip()

        for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.strptime(value, fmt).date()
            except ValueError:
                pass

    raise ValueError(f"Não foi possível converter a data: {value} ({type(value)})")


def get_next_order_number(cursor):
    cursor.execute("SELECT COALESCE(MAX(orderNumber), 0) + 1 FROM orders")
    return cursor.fetchone()[0]


def get_base_date(cursor):
    cursor.execute("""
        SELECT GREATEST(
            COALESCE(
                (
                    SELECT last_processed_order_date
                    FROM etl_watermark
                    WHERE pipeline_name = %s
                ),
                DATE('1900-01-01')
            ),
            COALESCE(
                (SELECT MAX(orderDate) FROM orders),
                DATE('1900-01-01')
            )
        )
    """, (PIPELINE_NAME,))

    result = cursor.fetchone()[0]
    return normalize_date(result)


def get_random_customer(cursor):
    cursor.execute("""
        SELECT customerNumber
        FROM customers
        ORDER BY RAND()
        LIMIT 1
    """)
    return cursor.fetchone()[0]


def get_random_product(cursor):
    cursor.execute("""
        SELECT productCode, buyPrice, MSRP
        FROM products
        ORDER BY RAND()
        LIMIT 1
    """)
    row = cursor.fetchone()

    return {
        "productCode": row[0],
        "buyPrice": float(row[1]),
        "MSRP": float(row[2]),
    }


def insert_order(cursor, order_number, order_date, customer_number):
    required_date = order_date + timedelta(days=7)
    shipped_date = order_date + timedelta(days=2)

    cursor.execute("""
        INSERT INTO orders (
            orderNumber,
            orderDate,
            requiredDate,
            shippedDate,
            status,
            comments,
            customerNumber
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, (
        order_number,
        order_date,
        required_date,
        shipped_date,
        "Shipped",
        "Simulated incremental order",
        customer_number,
    ))


def insert_order_detail(cursor, order_number, product, rng):
    quantity = rng.randint(1, 20)

    min_price = product["buyPrice"] * 1.20
    max_price = product["MSRP"]

    if max_price < min_price:
        max_price = min_price

    price_each = round(rng.uniform(min_price, max_price), 2)

    cursor.execute("""
        INSERT INTO orderdetails (
            orderNumber,
            productCode,
            quantityOrdered,
            priceEach,
            orderLineNumber
        )
        VALUES (%s, %s, %s, %s, %s)
    """, (
        order_number,
        product["productCode"],
        quantity,
        price_each,
        1,
    ))

    return quantity, price_each


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=5)
    parser.add_argument("--seed", type=int, default=None)
    args = parser.parse_args()

    if args.count <= 0:
        raise ValueError("--count deve ser maior que zero.")

    rng = random.Random(args.seed)

    conn = get_connection()
    cursor = conn.cursor()

    created_orders = []
    created_dates = []
    detail_rows = 0

    try:
        base_date = get_base_date(cursor)
        next_order_number = get_next_order_number(cursor)

        print(f"Data base encontrada: {base_date}")
        print(f"Próximo orderNumber: {next_order_number}")

        for i in range(args.count):
            order_number = next_order_number + i
            order_date = base_date + timedelta(days=i + 1)

            customer_number = get_random_customer(cursor)
            product = get_random_product(cursor)

            insert_order(
                cursor=cursor,
                order_number=order_number,
                order_date=order_date,
                customer_number=customer_number,
            )

            insert_order_detail(
                cursor=cursor,
                order_number=order_number,
                product=product,
                rng=rng,
            )

            created_orders.append(order_number)
            created_dates.append(order_date)
            detail_rows += 1

        conn.commit()

        print("\nSimulação concluída com sucesso.")
        print(f"Pedidos criados: {created_orders}")
        print(f"Faixa de datas: {min(created_dates)} até {max(created_dates)}")
        print(f"Linhas criadas em orderdetails: {detail_rows}")
        print("Observação: o etl_watermark NÃO foi atualizado por este script.")

    except Exception:
        conn.rollback()
        raise

    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    main()