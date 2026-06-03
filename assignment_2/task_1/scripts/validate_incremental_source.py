import argparse
import logging
import sys

from db_config import add_db_args, config_from_args, connect, setup_logging
from simulate_new_orders import PIPELINE_NAME, SIMULATION_COMMENT


LOGGER = logging.getLogger(__name__)
EXPECTED_SOURCE_TABLES = {
    "customers",
    "orders",
    "orderdetails",
    "products",
}
EXPECTED_WATERMARK_COLUMNS = {
    "pipeline_name": ("varchar", 64),
    "last_processed_order_date": ("date", None),
    "last_run_at": ("datetime", None),
    "last_run_status": ("varchar", 32),
}


def fetch_scalar(cursor, query, params=None):
    cursor.execute(query, params or ())
    return cursor.fetchone()[0]


def append_expected_table_failures(cursor, failures: list[str]) -> None:
    for table_name in sorted(EXPECTED_SOURCE_TABLES):
        exists = fetch_scalar(
            cursor,
            """
            SELECT COUNT(*)
            FROM information_schema.tables
            WHERE table_schema = DATABASE()
              AND table_name = %s
            """,
            (table_name,),
        )
        if exists != 1:
            failures.append(f"Required source table not found: {table_name}")
            continue

        row_count = fetch_scalar(cursor, f"SELECT COUNT(*) FROM `{table_name}`")
        if row_count < 1:
            failures.append(f"Required source table is empty: {table_name}")


def append_watermark_contract_failures(cursor, failures: list[str]) -> None:
    cursor.execute(
        """
        SELECT
            column_name AS column_name,
            data_type AS data_type,
            character_maximum_length AS character_maximum_length
        FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = 'etl_watermark'
        """
    )
    actual_columns = {row["column_name"]: row for row in cursor.fetchall()}
    for column_name, (expected_type, expected_length) in EXPECTED_WATERMARK_COLUMNS.items():
        column = actual_columns.get(column_name)
        if not column:
            failures.append(f"etl_watermark missing column: {column_name}")
            continue
        if column["data_type"].lower() != expected_type:
            failures.append(
                f"etl_watermark.{column_name} has type {column['data_type']}; expected {expected_type}"
            )
        if expected_length and column["character_maximum_length"] != expected_length:
            failures.append(
                f"etl_watermark.{column_name} has length {column['character_maximum_length']}; expected {expected_length}"
            )


def validate(connection, require_pending: bool) -> list[str]:
    failures = []

    with connection.cursor(dictionary=True) as cursor:
        LOGGER.info("Checking required classicmodels source tables")
        append_expected_table_failures(cursor, failures)

        LOGGER.info("Checking etl_watermark table")
        table_exists = fetch_scalar(
            cursor,
            """
            SELECT COUNT(*)
            FROM information_schema.tables
            WHERE table_schema = DATABASE()
              AND table_name = 'etl_watermark'
            """,
        )
        if table_exists != 1:
            failures.append("etl_watermark table does not exist")
            return failures

        append_watermark_contract_failures(cursor, failures)

        cursor.execute(
            """
            SELECT pipeline_name, last_processed_order_date, last_run_status
            FROM etl_watermark
            WHERE pipeline_name = %s
            """,
            (PIPELINE_NAME,),
        )
        watermark = cursor.fetchone()
        if not watermark:
            return [f"etl_watermark row not found for {PIPELINE_NAME}"]

        last_processed = watermark["last_processed_order_date"]
        if last_processed is None:
            failures.append("last_processed_order_date is NULL")

        max_order_date = fetch_scalar(cursor, "SELECT MAX(orderDate) FROM orders")
        has_pending = last_processed is not None and max_order_date is not None and max_order_date > last_processed
        if require_pending and not has_pending:
            failures.append("No pending orders: MAX(orders.orderDate) is not greater than watermark")

        orphan_orderdetails = fetch_scalar(
            cursor,
            """
            SELECT COUNT(*)
            FROM orderdetails od
            LEFT JOIN orders o ON o.orderNumber = od.orderNumber
            WHERE o.orderNumber IS NULL
            """,
        )
        if orphan_orderdetails:
            failures.append(f"{orphan_orderdetails} orderdetails rows reference missing orders")

        orphan_products = fetch_scalar(
            cursor,
            """
            SELECT COUNT(*)
            FROM orderdetails od
            LEFT JOIN products p ON p.productCode = od.productCode
            WHERE p.productCode IS NULL
            """,
        )
        if orphan_products:
            failures.append(f"{orphan_products} orderdetails rows reference missing products")

        orphan_simulated_orders = fetch_scalar(
            cursor,
            """
            SELECT COUNT(*)
            FROM orders o
            LEFT JOIN orderdetails od ON od.orderNumber = o.orderNumber
            WHERE o.comments = %s
              AND od.orderNumber IS NULL
            """,
            (SIMULATION_COMMENT,),
        )
        if orphan_simulated_orders:
            failures.append(f"{orphan_simulated_orders} simulated orders have no orderdetails rows")

        invalid_sales_rows = fetch_scalar(
            cursor,
            """
            SELECT COUNT(*)
            FROM orders o
            JOIN orderdetails od ON od.orderNumber = o.orderNumber
            WHERE o.comments = %s
              AND (od.quantityOrdered <= 0 OR od.priceEach <= 0)
            """,
            (SIMULATION_COMMENT,),
        )
        if invalid_sales_rows:
            failures.append(f"{invalid_sales_rows} simulated orderdetails rows have invalid sales_amount inputs")

        print(f"Watermark date: {last_processed}")
        print(f"Max orderDate: {max_order_date}")
        print(f"Pending orders after watermark: {'yes' if has_pending else 'no'}")
        print(f"Orphan orderdetails rows: {orphan_orderdetails}")
        print(f"Orderdetails with missing products: {orphan_products}")
        print(f"Simulated orders without details: {orphan_simulated_orders}")

    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate classicmodels incremental source readiness.")
    add_db_args(parser)
    parser.add_argument(
        "--require-pending",
        action="store_true",
        help="Fail when MAX(orders.orderDate) is not greater than the watermark.",
    )
    args = parser.parse_args()
    setup_logging(args.verbose)

    try:
        config = config_from_args(args)
        connection = connect(config)
        try:
            failures = validate(connection, args.require_pending)
        finally:
            connection.close()

        if failures:
            for failure in failures:
                print(f"FAIL: {failure}", file=sys.stderr)
            return 1

        print("Validation succeeded")
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
