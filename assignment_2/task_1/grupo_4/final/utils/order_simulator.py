"""Simulate new OLTP orders strictly after the current watermark baseline."""

from __future__ import annotations

import random
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Sequence

from pymysql.connections import Connection

from src.models import SimulatedLineItem, SimulationSummary
from utils.database import execute, fetch_all, fetch_one
from utils.watermark import get_max_order_date, get_watermark

# --- Simulation defaults (CLI may override count / lines_per_order) ---
DEFAULT_ORDER_COUNT = 5
DEFAULT_LINES_PER_ORDER = 2
MIN_ORDER_COUNT = 1

# --- Weekday logic (Mon=0 … Sun=6) ---
SATURDAY_WEEKDAY = 5

# --- orderdetails / pricing ---
PRICE_QUANTIZE_STEP = Decimal("0.01")
MIN_LINE_QUANTITY = 1
MAX_LINE_QUANTITY = 50
ORDER_LINE_NUMBER_START = 1
PRICE_RANDOM_LOW = 0.0
PRICE_RANDOM_HIGH = 1.0

# --- orders row defaults ---
ORDER_STATUS = "In Process"
ORDER_COMMENTS = "Simulated order for incremental ETL"


def _next_business_day(start: date) -> date:
    """Advance to the next weekday (Mon–Fri) to ease Task 2 date partitioning."""
    candidate = start + timedelta(days=1)
    while candidate.weekday() >= SATURDAY_WEEKDAY:
        candidate += timedelta(days=1)
    return candidate


def _quantize_price(value: Decimal) -> Decimal:
    """Match orderdetails.priceEach DECIMAL(10,2) precision."""
    return value.quantize(PRICE_QUANTIZE_STEP, rounding=ROUND_HALF_UP)


def _load_reference_data(conn: Connection) -> tuple[list[int], list[dict]]:
    """Load existing customers and products required for valid FK inserts."""
    customers = fetch_all(conn, "SELECT customerNumber FROM customers")
    products = fetch_all(
        conn,
        """
        SELECT productCode, buyPrice, MSRP
        FROM products
        WHERE buyPrice IS NOT NULL AND MSRP IS NOT NULL
        """,
    )
    if not customers:
        raise RuntimeError("No customers found in classicmodels.customers.")
    if not products:
        raise RuntimeError("No products found in classicmodels.products.")
    customer_ids = [int(row["customerNumber"]) for row in customers]
    return customer_ids, products


def _resolve_baseline_date(conn: Connection) -> date:
    """
    First simulated orderDate must be strictly after both:
    - etl_watermark.last_processed_order_date
    - MAX(orders.orderDate)
    """
    watermark = get_watermark(conn)
    watermark_date = watermark.last_processed_order_date if watermark else None
    max_order_date = get_max_order_date(conn)

    candidates = [d for d in (watermark_date, max_order_date) if d is not None]
    if not candidates:
        raise RuntimeError("Cannot determine baseline order date (orders table empty?).")
    return max(candidates)


def _next_order_number(conn: Connection) -> int:
    """classicmodels.orders.orderNumber is not AUTO_INCREMENT; allocate manually."""
    row = fetch_one(conn, "SELECT COALESCE(MAX(orderNumber), 0) + 1 AS next_id FROM orders")
    return int(row["next_id"])


def _pick_unit_price(product: dict, rng: random.Random) -> Decimal:
    """
    Derive a realistic unit price between buyPrice and MSRP.

    Star-schema rule: sales_amount = quantityOrdered * priceEach.
    """
    buy = Decimal(str(product["buyPrice"]))
    msrp = Decimal(str(product["MSRP"]))
    if msrp <= buy:
        return _quantize_price(msrp)
    # Random price in [buy, msrp] for variety while staying business-plausible.
    fraction = Decimal(str(rng.uniform(PRICE_RANDOM_LOW, PRICE_RANDOM_HIGH)))
    price = buy + (msrp - buy) * fraction
    return _quantize_price(price)


def _insert_order_with_details(
    conn: Connection,
    *,
    order_number: int,
    order_date: date,
    customer_number: int,
    products: Sequence[dict],
    rng: random.Random,
    lines_per_order: int,
) -> list[SimulatedLineItem]:
    """Insert one orders row and at least one orderdetails row inside the open transaction."""
    required_date = _next_business_day(order_date)
    shipped_date = None
    status = ORDER_STATUS
    comments = ORDER_COMMENTS

    execute(
        conn,
        """
        INSERT INTO orders (
            orderNumber, orderDate, requiredDate, shippedDate,
            status, comments, customerNumber
        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (
            order_number,
            order_date,
            required_date,
            shipped_date,
            status,
            comments,
            customer_number,
        ),
    )

    chosen_products = rng.sample(list(products), k=min(lines_per_order, len(products)))
    line_items: list[SimulatedLineItem] = []

    for line_no, product in enumerate(chosen_products, start=ORDER_LINE_NUMBER_START):
        quantity = rng.randint(MIN_LINE_QUANTITY, MAX_LINE_QUANTITY)
        price_each = _pick_unit_price(product, rng)
        execute(
            conn,
            """
            INSERT INTO orderdetails (
                orderNumber, productCode, quantityOrdered, priceEach, orderLineNumber
            ) VALUES (%s, %s, %s, %s, %s)
            """,
            (
                order_number,
                product["productCode"],
                quantity,
                price_each,
                line_no,
            ),
        )
        line_items.append(
            SimulatedLineItem(
                order_number=order_number,
                product_code=product["productCode"],
                quantity_ordered=quantity,
                price_each=price_each,
                order_line_number=line_no,
            )
        )

    return line_items


def simulate_orders(
    conn: Connection,
    count: int = DEFAULT_ORDER_COUNT,
    seed: int | None = None,
    lines_per_order: int = DEFAULT_LINES_PER_ORDER,
) -> SimulationSummary:
    """
    Create `count` new orders with orderDate strictly after the watermark baseline.
    Each order is committed in its own transaction for safe re-runs.
    """
    if count < MIN_ORDER_COUNT:
        raise ValueError(f"count must be >= {MIN_ORDER_COUNT}")

    rng = random.Random(seed)
    customer_ids, products = _load_reference_data(conn)

    baseline = _resolve_baseline_date(conn)
    order_date = _next_business_day(baseline)

    order_numbers: list[int] = []
    all_line_items: list[SimulatedLineItem] = []
    order_dates: list[date] = []

    # Single MAX lookup; orderNumber is not AUTO_INCREMENT in classicmodels.
    next_order_number = _next_order_number(conn)

    for _ in range(count):
        order_number = next_order_number
        next_order_number += 1
        customer_number = rng.choice(customer_ids)
        current_order_date = order_date

        try:
            line_items = _insert_order_with_details(
                conn,
                order_number=order_number,
                order_date=current_order_date,
                customer_number=customer_number,
                products=products,
                rng=rng,
                lines_per_order=lines_per_order,
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise

        order_numbers.append(order_number)
        order_dates.append(current_order_date)
        all_line_items.extend(line_items)
        order_date = _next_business_day(order_date)

    return SimulationSummary(
        order_numbers=order_numbers,
        min_order_date=min(order_dates),
        max_order_date=max(order_dates),
        orderdetails_rows=len(all_line_items),
        line_items=all_line_items,
    )
