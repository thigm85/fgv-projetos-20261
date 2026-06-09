from __future__ import annotations

import argparse
import random
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from common import PIPELINE_NAME, connect, fetch_one_value


def parse_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise argparse.ArgumentTypeError("date must use YYYY-MM-DD format") from exc


def next_order_date(value: date, allow_weekends: bool) -> date:
    candidate = value + timedelta(days=1)
    if allow_weekends:
        return candidate
    while candidate.weekday() >= 5:
        candidate += timedelta(days=1)
    return candidate


def get_baseline_date(cursor: Any) -> date:
    watermark = fetch_one_value(
        cursor,
        "SELECT last_processed_order_date FROM etl_watermark WHERE pipeline_name = %s",
        (PIPELINE_NAME,),
    )
    max_order_date = fetch_one_value(cursor, "SELECT MAX(orderDate) FROM orders")
    candidates = [value for value in (watermark, max_order_date) if value is not None]
    if not candidates:
        raise RuntimeError("Could not calculate a baseline order date.")
    return max(candidates)


def get_next_order_number(cursor: Any) -> int:
    current_max = fetch_one_value(cursor, "SELECT MAX(orderNumber) FROM orders")
    if current_max is None:
        return 1
    return int(current_max) + 1


def load_reference_data(cursor: Any) -> tuple[list[int], list[dict[str, Any]]]:
    cursor.execute("SELECT customerNumber FROM customers")
    customers = [int(row["customerNumber"]) for row in cursor.fetchall()]

    cursor.execute("SELECT productCode, MSRP, buyPrice FROM products")
    products = list(cursor.fetchall())

    if not customers:
        raise RuntimeError("customers is empty.")
    if not products:
        raise RuntimeError("products is empty.")

    return customers, products


def choose_price(product: dict[str, Any]) -> Decimal:
    reference_price = product["MSRP"] or product["buyPrice"] or Decimal("1.00")
    return Decimal(str(reference_price)).quantize(Decimal("0.01"))


def simulate_new_orders(
    count: int,
    seed: int | None,
    start_date: date | None,
    allow_weekends: bool,
    dry_run: bool,
) -> dict[str, Any]:
    if count <= 0:
        raise ValueError("--count must be greater than zero.")

    rng = random.Random(seed)

    with connect() as connection:
        try:
            with connection.cursor() as cursor:
                customers, products = load_reference_data(cursor)
                baseline_date = get_baseline_date(cursor)
                current_date = start_date or baseline_date

                if start_date is not None and start_date <= baseline_date:
                    raise ValueError(
                        f"--start-date must be after baseline {baseline_date}; got {start_date}."
                    )

                order_number = get_next_order_number(cursor)
                created_order_numbers: list[int] = []
                created_dates: list[date] = []
                details_count = 0

                for index in range(count):
                    current_order_number = order_number + index
                    if start_date is None or index > 0:
                        current_date = next_order_date(current_date, allow_weekends)

                    required_date = current_date + timedelta(days=7)
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
                            current_date,
                            required_date,
                            "Simulated order for incremental source",
                            customer_number,
                        ),
                    )

                    line_count = rng.randint(1, min(3, len(products)))
                    selected_products = rng.sample(products, line_count)

                    for line_number, product in enumerate(selected_products, start=1):
                        quantity = rng.randint(1, 20)
                        price_each = choose_price(product)

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
                    created_dates.append(current_date)

            if dry_run:
                connection.rollback()
            else:
                connection.commit()
        except Exception:
            connection.rollback()
            raise

    return {
        "dry_run": dry_run,
        "order_numbers": created_order_numbers,
        "start_date": min(created_dates),
        "end_date": max(created_dates),
        "details_count": details_count,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Simulate incremental classicmodels orders.")
    parser.add_argument("--count", type=int, default=5, help="Number of orders to create.")
    parser.add_argument("--seed", type=int, default=None, help="Optional seed for reproducible demos.")
    parser.add_argument("--start-date", type=parse_date, default=None, help="First order date, YYYY-MM-DD.")
    parser.add_argument("--allow-weekends", action="store_true", help="Allow simulated dates on weekends.")
    parser.add_argument("--dry-run", action="store_true", help="Rollback after planning and inserting rows.")
    args = parser.parse_args()

    try:
        summary = simulate_new_orders(
            count=args.count,
            seed=args.seed,
            start_date=args.start_date,
            allow_weekends=args.allow_weekends,
            dry_run=args.dry_run,
        )
    except Exception as exc:
        print(f"Failed to simulate orders: {exc}", file=sys.stderr)
        return 1

    prefix = "Dry run completed" if summary["dry_run"] else "Simulation completed"
    print(f"{prefix}.")
    print(f"Orders: {summary['order_numbers']}")
    print(f"Date range: {summary['start_date']} to {summary['end_date']}")
    print(f"orderdetails rows: {summary['details_count']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
