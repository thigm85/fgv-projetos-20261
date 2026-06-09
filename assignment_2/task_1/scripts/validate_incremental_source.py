from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from typing import Any

from common import PIPELINE_NAME, connect


@dataclass
class ValidationSummary:
    watermark_date: Any = None
    max_order_date: Any = None
    pending_orders: int = 0
    pending_orderdetails: int = 0
    orphan_orders: int = 0


def validate(require_pending: bool) -> tuple[list[str], ValidationSummary]:
    errors: list[str] = []
    summary = ValidationSummary()

    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT COUNT(*) AS total
                FROM information_schema.tables
                WHERE table_schema = DATABASE()
                  AND table_name = 'etl_watermark'
                """
            )
            if cursor.fetchone()["total"] != 1:
                return ["etl_watermark table does not exist."], summary

            cursor.execute(
                """
                SELECT last_processed_order_date, last_run_at, last_run_status
                FROM etl_watermark
                WHERE pipeline_name = %s
                """,
                (PIPELINE_NAME,),
            )
            watermark = cursor.fetchone()
            if watermark is None:
                return [f"Missing etl_watermark row for {PIPELINE_NAME}."], summary

            summary.watermark_date = watermark["last_processed_order_date"]
            if summary.watermark_date is None:
                errors.append("last_processed_order_date is NULL.")

            cursor.execute("SELECT MAX(orderDate) AS max_order_date FROM orders")
            summary.max_order_date = cursor.fetchone()["max_order_date"]
            if summary.max_order_date is None:
                errors.append("orders has no rows.")
            elif summary.watermark_date is not None:
                if summary.max_order_date < summary.watermark_date:
                    errors.append(
                        "MAX(orderDate) is earlier than the watermark: "
                        f"{summary.max_order_date} < {summary.watermark_date}."
                    )
                elif require_pending and summary.max_order_date <= summary.watermark_date:
                    errors.append(
                        "No pending orders by date: "
                        f"MAX(orderDate)={summary.max_order_date}, "
                        f"watermark={summary.watermark_date}."
                    )

            cursor.execute(
                """
                SELECT COUNT(DISTINCT o.orderNumber) AS total
                FROM orders o
                LEFT JOIN orderdetails od ON od.orderNumber = o.orderNumber
                WHERE od.orderNumber IS NULL
                """
            )
            summary.orphan_orders = int(cursor.fetchone()["total"])
            if summary.orphan_orders:
                errors.append(f"{summary.orphan_orders} orders have no orderdetails rows.")

            if summary.watermark_date is not None:
                cursor.execute(
                    """
                    SELECT
                        COUNT(DISTINCT o.orderNumber) AS pending_orders,
                        COUNT(od.orderNumber) AS pending_orderdetails
                    FROM orders o
                    LEFT JOIN orderdetails od ON od.orderNumber = o.orderNumber
                    WHERE o.orderDate > %s
                    """,
                    (summary.watermark_date,),
                )
                pending = cursor.fetchone()
                summary.pending_orders = int(pending["pending_orders"])
                summary.pending_orderdetails = int(pending["pending_orderdetails"])

                if require_pending and summary.pending_orders == 0:
                    errors.append("No pending orders found after the watermark.")
                if require_pending and summary.pending_orderdetails == 0:
                    errors.append("No pending orderdetails found after the watermark.")

    return errors, summary


def print_summary(summary: ValidationSummary) -> None:
    print("Validation summary:")
    print(f"- watermark_date: {summary.watermark_date}")
    print(f"- max_order_date: {summary.max_order_date}")
    print(f"- pending_orders: {summary.pending_orders}")
    print(f"- pending_orderdetails: {summary.pending_orderdetails}")
    print(f"- orphan_orders: {summary.orphan_orders}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the classicmodels incremental source.")
    parser.add_argument(
        "--require-pending",
        action="store_true",
        help="Fail unless orders exist after the current watermark.",
    )
    parser.add_argument("--quiet", action="store_true", help="Only print failures.")
    args = parser.parse_args()

    try:
        errors, summary = validate(args.require_pending)
    except Exception as exc:
        print(f"Validation crashed: {exc}", file=sys.stderr)
        return 1

    if errors:
        print("Validation failed:")
        for error in errors:
            print(f"- {error}")
        if not args.quiet:
            print_summary(summary)
        return 1

    if not args.quiet:
        print("Validation passed.")
        print_summary(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())

