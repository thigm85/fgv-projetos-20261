import datetime
import random

from db import get_connection
from watermark import get_orders_max_date, get_watermark


def choose_random_existing_items(cursor):
    cursor.execute("SELECT customerNumber FROM customers ORDER BY RAND() LIMIT 1")
    customer = cursor.fetchone()
    if not customer:
        raise SystemExit("No customers found in the database.")

    cursor.execute(
        "SELECT productCode, buyPrice FROM products ORDER BY RAND() LIMIT 1"
    )
    product = cursor.fetchone()
    if not product:
        raise SystemExit("No products found in the database.")

    return customer["customerNumber"], product["productCode"], float(product["buyPrice"])


def simulate_new_orders(args):
    random.seed(args.seed)
    with get_connection() as conn:
        with conn.cursor() as cursor:
            watermark = get_watermark(cursor)
            if watermark is None:
                raise SystemExit(
                    "Watermark record missing. Run the init-watermark command first."
                )

            base_watermark = watermark["last_processed_order_date"]
            max_order_date = get_orders_max_date(cursor)
            if max_order_date is None and base_watermark is None:
                base_date = datetime.date.today() - datetime.timedelta(days=1)
            else:
                base_date = max(
                    date for date in (base_watermark, max_order_date) if date is not None
                )

            cursor.execute("SELECT MAX(orderNumber) AS next_number FROM orders")
            row = cursor.fetchone()
            next_order_number = int(row["next_number"] or 0) + 1

            created_orders = []
            created_details = 0
            first_date = None
            last_date = None

            for index in range(args.count):
                order_number = next_order_number + index
                order_date = base_date + datetime.timedelta(days=index + 1)
                required_date = order_date + datetime.timedelta(days=7)
                shipped_date = order_date + datetime.timedelta(days=1)
                customer_number, product_code, buy_price = choose_random_existing_items(cursor)
                quantity = random.randint(1, 10)
                price_each = round(buy_price, 2)
                order_line_number = 1

                cursor.execute(
                    "INSERT INTO orders "
                    "(orderNumber, orderDate, requiredDate, shippedDate, status, comments, customerNumber) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    (
                        order_number,
                        order_date,
                        required_date,
                        shipped_date,
                        "Shipped",
                        None,
                        customer_number,
                    ),
                )

                cursor.execute(
                    "INSERT INTO orderdetails "
                    "(orderNumber, productCode, quantityOrdered, priceEach, orderLineNumber) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (
                        order_number,
                        product_code,
                        quantity,
                        price_each,
                        order_line_number,
                    ),
                )

                created_orders.append(order_number)
                created_details += 1
                first_date = first_date or order_date
                last_date = order_date

            conn.commit()

    print("Simulation completed")
    print(f"Created orders: {created_orders}")
    print(f"Dates: {first_date} -> {last_date}")
    print(f"Order detail rows inserted: {created_details}")
