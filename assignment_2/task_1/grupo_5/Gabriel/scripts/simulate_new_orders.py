import argparse
import os
import random
import sys
from datetime import date, timedelta

import pymysql

RDS_HOST = os.environ["RDS_HOST"]
RDS_PORT = int(os.environ.get("RDS_PORT", 3306))
RDS_USER = os.environ["RDS_USER"]
RDS_PASSWORD = os.environ["RDS_PASSWORD"]
RDS_DB = os.environ.get("RDS_DB", "classicmodels")


def parse_args():
    parser = argparse.ArgumentParser(description="Simula novos pedidos no classicmodels")
    parser.add_argument("--count", type=int, default=5, help="Número de pedidos a criar")
    parser.add_argument("--seed", type=int, default=None, help="Semente para reprodutibilidade")
    return parser.parse_args()


def fetch_baseline(cur) -> tuple[list, list, date]:
    cur.execute("SELECT customerNumber FROM customers")
    customers = [r[0] for r in cur.fetchall()]

    cur.execute("SELECT productCode, buyPrice FROM products")
    products = cur.fetchall()

    cur.execute(
        """
        SELECT GREATEST(
            COALESCE((SELECT last_processed_order_date FROM etl_watermark WHERE pipeline_name = 'classicmodels_sales'), '1900-01-01'),
            MAX(orderDate)
        )
        FROM orders
        """
    )
    row = cur.fetchone()
    baseline_date = row[0] if row[0] else date.today()
    if isinstance(baseline_date, str):
        baseline_date = date.fromisoformat(baseline_date)

    return customers, products, baseline_date


def next_order_number(cur) -> int:
    cur.execute("SELECT MAX(orderNumber) FROM orders")
    max_num = cur.fetchone()[0]
    return (max_num or 10000) + 1


def main():
    args = parse_args()
    rng = random.Random(args.seed)

    conn = pymysql.connect(
        host=RDS_HOST,
        port=RDS_PORT,
        user=RDS_USER,
        password=RDS_PASSWORD,
        database=RDS_DB,
        autocommit=False,
        charset="utf8mb4",
    )

    created_orders = []

    with conn.cursor() as cur:
        customers, products, baseline_date = fetch_baseline(cur)

        if not customers or not products:
            print("Sem clientes ou produtos na base. Abortando.")
            conn.close()
            sys.exit(1)

        current_date = baseline_date

        for i in range(args.count):
            current_date += timedelta(days=rng.randint(1, 3))
            order_number = next_order_number(cur)
            customer_number = rng.choice(customers)

            num_lines = rng.randint(1, 3)
            chosen_products = rng.sample(products, min(num_lines, len(products)))

            cur.execute(
                """
                INSERT INTO orders (orderNumber, orderDate, requiredDate, shippedDate, status, customerNumber)
                VALUES (%s, %s, %s, %s, 'Shipped', %s)
                """,
                (
                    order_number,
                    current_date.isoformat(),
                    (current_date + timedelta(days=7)).isoformat(),
                    (current_date + timedelta(days=3)).isoformat(),
                    customer_number,
                ),
            )

            detail_rows = 0
            for line_num, (product_code, buy_price) in enumerate(chosen_products, start=1):
                quantity = rng.randint(1, 10)
                price_each = round(float(buy_price) * rng.uniform(1.1, 1.5), 2)

                cur.execute(
                    """
                    INSERT INTO orderdetails (orderNumber, productCode, quantityOrdered, priceEach, orderLineNumber)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (order_number, product_code, quantity, price_each, line_num),
                )
                detail_rows += 1

            conn.commit()
            created_orders.append(
                {
                    "orderNumber": order_number,
                    "orderDate": current_date.isoformat(),
                    "customerNumber": customer_number,
                    "detailRows": detail_rows,
                }
            )

    conn.close()

    print(f"\nResumo — {len(created_orders)} pedidos criados:")
    for o in created_orders:
        print(
            f"  orderNumber={o['orderNumber']}  date={o['orderDate']}  "
            f"customer={o['customerNumber']}  linhas_detalhe={o['detailRows']}"
        )

    dates = [o["orderDate"] for o in created_orders]
    print(f"\nFaixa de datas: {min(dates)} → {max(dates)}")
    total_lines = sum(o["detailRows"] for o in created_orders)
    print(f"Total de linhas em orderdetails: {total_lines}")


if __name__ == "__main__":
    main()
