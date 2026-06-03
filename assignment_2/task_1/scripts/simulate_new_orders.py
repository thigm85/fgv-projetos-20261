import argparse
import logging
import random
import sys
from datetime import timedelta
from decimal import Decimal

from db_config import add_db_args, config_from_args, connect, setup_logging


PIPELINE_NAME = "classicmodels_sales"
SIMULATION_COMMENT = "assignment_2_task_1_simulated"
LOGGER = logging.getLogger(__name__)


def fetch_scalar(cursor, query, params=None):
    cursor.execute(query, params or ())
    return cursor.fetchone()[0]


def simulate_orders(connection, count: int, seed: int | None, dry_run: bool):
    rng = random.Random(seed)

    with connection.cursor(dictionary=True) as cursor:
        LOGGER.info("Reading current watermark")
        watermark_date = fetch_scalar(
            cursor,
            """
            SELECT last_processed_order_date
            FROM etl_watermark
            WHERE pipeline_name = %s
            """,
            (PIPELINE_NAME,),
        )
        if watermark_date is None:
            raise RuntimeError("Run scripts/init_watermark.py before simulating new orders")

        LOGGER.info("Locking latest order row to generate new orderNumber values safely")
        cursor.execute("SELECT orderNumber FROM orders ORDER BY orderNumber DESC LIMIT 1 FOR UPDATE")
        max_order_number = cursor.fetchone()["orderNumber"]
        max_order_date = fetch_scalar(cursor, "SELECT MAX(orderDate) FROM orders")
        base_date = max(watermark_date, max_order_date)

        LOGGER.info("Loading valid customers and products")
        cursor.execute("SELECT customerNumber FROM customers ORDER BY customerNumber")
        customers = [row["customerNumber"] for row in cursor.fetchall()]
        cursor.execute("SELECT productCode, MSRP FROM products ORDER BY productCode")
        products = cursor.fetchall()
        if not customers or not products:
            raise RuntimeError("customers and products must contain rows")

        created_orders = []
        detail_rows = 0

        for offset in range(1, count + 1):
            order_number = max_order_number + offset
            order_date = base_date + timedelta(days=offset)
            required_date = order_date + timedelta(days=7)
            customer_number = rng.choice(customers)
            product = rng.choice(products)
            quantity_ordered = rng.randint(1, 60)
            price_each = Decimal(product["MSRP"]).quantize(Decimal("0.01"))

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
                (order_number, order_date, required_date, SIMULATION_COMMENT, customer_number),
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
                VALUES (%s, %s, %s, %s, 1)
                """,
                (order_number, product["productCode"], quantity_ordered, price_each),
            )
            created_orders.append(
                {
                    "order_number": order_number,
                    "order_date": order_date,
                    "product_code": product["productCode"],
                    "quantity_ordered": quantity_ordered,
                    "price_each": price_each,
                    "sales_amount": Decimal(quantity_ordered) * price_each,
                }
            )
            detail_rows += 1

    if dry_run:
        connection.rollback()
        LOGGER.info("Dry-run finished; transaction rolled back")
    else:
        connection.commit()
        LOGGER.info("Simulation committed successfully")
    return created_orders, detail_rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Insert simulated incremental classicmodels orders.")
    add_db_args(parser)
    parser.add_argument("--count", type=int, default=5, help="Number of orders to create.")
    parser.add_argument("--seed", type=int, default=None, help="Optional random seed for reproducible demos.")
    parser.add_argument("--dry-run", action="store_true", help="Build the simulation plan and roll back instead of committing.")
    args = parser.parse_args()
    setup_logging(args.verbose)

    if args.count < 1:
        print("ERROR: --count must be greater than zero", file=sys.stderr)
        return 1

    try:
        config = config_from_args(args)
        connection = connect(config)
        try:
            created_orders, detail_rows = simulate_orders(connection, args.count, args.seed, args.dry_run)
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

        dates = [item["order_date"] for item in created_orders]
        ids = [str(item["order_number"]) for item in created_orders]
        print(f"Created orders: {', '.join(ids)}")
        print(f"Date range: {min(dates)} to {max(dates)}")
        print(f"Inserted orderdetails rows: {detail_rows}")
        print(f"Committed: {'no (dry-run)' if args.dry_run else 'yes'}")
        print("sales_amount rule: quantityOrdered * priceEach")
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
