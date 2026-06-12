"""
Simulate N new orders after the current watermark date.

Each run inserts orders with dates strictly after MAX(orderDate, watermark),
so the incremental ETL will always pick them up on the next run.

Usage:
    python simulate_new_orders.py [--count N] [--seed S]
"""

import argparse
import os
import random
from datetime import timedelta
from decimal import Decimal

import pymysql
from dotenv import load_dotenv

PIPELINE_NAME = "classicmodels_sales"


def _parse_args():
    p = argparse.ArgumentParser(description="Simulate new orders for incremental ETL testing.")
    p.add_argument("--count", type=int, default=5, help="Number of orders to create (default: 5)")
    p.add_argument("--seed", type=int, default=None, help="Optional RNG seed for reproducibility")
    return p.parse_args()


def _connect():
    load_dotenv()
    return pymysql.connect(
        host=os.environ["DB_HOST"],
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        database=os.getenv("DB_NAME", "classicmodels"),
        cursorclass=pymysql.cursors.DictCursor,
    )


def main():
    args = _parse_args()
    if args.count <= 0:
        raise ValueError("--count must be greater than zero.")

    rng = random.Random(args.seed)
    conn = _connect()

    try:
        with conn.cursor() as cur:
            # Lock watermark row to get a consistent base date
            cur.execute(
                "SELECT last_processed_order_date FROM etl_watermark WHERE pipeline_name = %s FOR UPDATE",
                (PIPELINE_NAME,),
            )
            wm = cur.fetchone()
            if not wm or wm["last_processed_order_date"] is None:
                raise RuntimeError("Run init_watermark.py before simulating orders.")

            cur.execute("SELECT MAX(orderDate) AS max_dt FROM orders")
            max_order_dt = cur.fetchone()["max_dt"]

            # Base date is always at least 1 day after both the watermark and the last order
            base_date = max(
                wm["last_processed_order_date"],
                max_order_dt.date() if hasattr(max_order_dt, "date") else max_order_dt,
            )

            cur.execute("SELECT customerNumber FROM customers ORDER BY customerNumber")
            customers = [r["customerNumber"] for r in cur.fetchall()]

            cur.execute(
                "SELECT productCode, COALESCE(MSRP, buyPrice) AS price FROM products WHERE COALESCE(MSRP, buyPrice) IS NOT NULL"
            )
            products = cur.fetchall()

            if not customers or not products:
                raise RuntimeError("Not enough customers or products to simulate orders.")

            cur.execute("SELECT COALESCE(MAX(orderNumber), 0) + 1 AS next_id FROM orders")
            next_id = cur.fetchone()["next_id"]

            created = []
            for i in range(args.count):
                order_no = next_id + i
                order_date = base_date + timedelta(days=i + 1)
                required_date = order_date + timedelta(days=7)
                customer = rng.choice(customers)
                product = rng.choice(products)
                qty = rng.randint(1, 20)
                price = Decimal(str(product["price"])).quantize(Decimal("0.01"))

                cur.execute(
                    """
                    INSERT INTO orders
                        (orderNumber, orderDate, requiredDate, shippedDate,
                         status, comments, customerNumber)
                    VALUES (%s, %s, %s, NULL, 'In Process',
                            'Simulated — Assignment 2 Task 2', %s)
                    """,
                    (order_no, order_date, required_date, customer),
                )
                cur.execute(
                    """
                    INSERT INTO orderdetails
                        (orderNumber, productCode, quantityOrdered, priceEach, orderLineNumber)
                    VALUES (%s, %s, %s, %s, 1)
                    """,
                    (order_no, product["productCode"], qty, price),
                )
                created.append((order_no, order_date))

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    dates = [d for _, d in created]
    print("Simulation complete.")
    print(f"  orders created : {[n for n, _ in created]}")
    print(f"  date range     : {min(dates)} → {max(dates)}")
    print(f"  orderdetails   : {len(created)}")
    print("  watermark      : NOT updated (ETL job will advance it)")


if __name__ == "__main__":
    main()
