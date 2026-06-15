import random

from datetime import timedelta

from utils.database import get_connection
from utils.watermark import (
    PIPELINE_NAME,
    initialize_watermark,
    get_watermark
)

from utils.validator import run_all_checks


def task_init_watermark():

    conn = get_connection()

    max_date = initialize_watermark(conn)

    print("Watermark initialized")
    print("Last processed order date:", max_date)

    conn.close()

    return 0


def task_validate():

    conn = get_connection()

    results = run_all_checks(conn)

    success = True

    print()

    for name, passed in results:

        status = "PASS" if passed else "FAIL"

        print(f"[{status}] {name}")

        if not passed:
            success = False

    conn.close()

    return 0 if success else 1


def task_simulate_orders(count=5, seed=None):

    if seed is not None:
        random.seed(seed)

    conn = get_connection()

    cursor = conn.cursor()

    watermark_date = get_watermark(conn)

    cursor.execute("""
    SELECT MAX(orderDate)
    FROM orders
    """)

    max_order_date = cursor.fetchone()[0]

    base_date = max(
        watermark_date,
        max_order_date
    )

    cursor.execute("""
    SELECT MAX(orderNumber)
    FROM orders
    """)

    next_order_number = cursor.fetchone()[0] + 1

    created_orders = []

    for i in range(count):

        cursor.execute("""
        SELECT customerNumber
        FROM customers
        ORDER BY RAND()
        LIMIT 1
        """)

        customer_number = cursor.fetchone()[0]

        cursor.execute("""
        SELECT productCode,buyPrice
        FROM products
        ORDER BY RAND()
        LIMIT 1
        """)

        product_code, buy_price = cursor.fetchone()

        order_date = base_date + timedelta(days=i + 1)

        required_date = order_date + timedelta(days=7)

        quantity = random.randint(1, 20)

        price_each = round(
            float(buy_price) * 1.3,
            2
        )

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
        VALUES (
            %s,%s,%s,%s,%s,%s,%s
        )
        """, (
            next_order_number,
            order_date,
            required_date,
            None,
            "In Process",
            "Simulated order",
            customer_number
        ))

        cursor.execute("""
        INSERT INTO orderdetails (
            orderNumber,
            productCode,
            quantityOrdered,
            priceEach,
            orderLineNumber
        )
        VALUES (
            %s,%s,%s,%s,%s
        )
        """, (
            next_order_number,
            product_code,
            quantity,
            price_each,
            1
        ))

        created_orders.append(
            next_order_number
        )

        next_order_number += 1

    conn.commit()

    print("\nOrders created:")

    for order_id in created_orders:
        print(order_id)

    conn.close()

    return 0