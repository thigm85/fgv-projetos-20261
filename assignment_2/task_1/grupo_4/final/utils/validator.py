"""
Reproducible checks that the incremental OLTP source is ready for ETL.

Public API
----------
- run_all_checks   — full validation suite
- print_results    — CLI-friendly output; returns True if all passed

Individual checks (also used by the suite):
1. validate_watermark_table_exists
2. validate_watermark_not_null
3. validate_pending_orders
4. validate_orderdetails_integrity
"""

from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from pymysql.connections import Connection
from src.models import Watermark
from utils.config import PIPELINE_NAME, WATERMARK_TABLE
from utils.database import fetch_all, fetch_one
from utils.watermark import _to_date, get_max_order_date, get_watermark

# ---------------------------------------------------------------------------
# Check identifiers (stable names in logs and scripts)
# ---------------------------------------------------------------------------

CHECK_WATERMARK_TABLE = "watermark_table_exists"
CHECK_WATERMARK_PIPELINE_ROW = "watermark_pipeline_row"
CHECK_WATERMARK_DATE = "watermark_date_not_null"
CHECK_PENDING_ORDERS = "pending_orders"
CHECK_ORDERDETAILS = "orderdetails_integrity"

INIT_HINT = "run init_watermark.py first."

# Minimum valid line values (aligned with order_simulator quantity rules)
MIN_VALID_QUANTITY = 1
MIN_VALID_PRICE = 0

# ---------------------------------------------------------------------------
# SQL
# ---------------------------------------------------------------------------

SQL_WATERMARK_TABLE_EXISTS = """
SELECT COUNT(*) AS table_exists
FROM information_schema.tables
WHERE table_schema = DATABASE()
  AND table_name = %s
"""

SQL_ORDERS_WITHOUT_ORDERDETAILS = """
SELECT o.orderNumber
FROM orders o
LEFT JOIN orderdetails od ON od.orderNumber = o.orderNumber
WHERE o.orderDate > %s
GROUP BY o.orderNumber
HAVING COUNT(od.productCode) = 0
"""

SQL_INVALID_ORDERDETAILS_BEYOND_WATERMARK = """
SELECT od.orderNumber, od.productCode, od.quantityOrdered, od.priceEach
FROM orderdetails od
INNER JOIN orders o ON o.orderNumber = od.orderNumber
WHERE o.orderDate > %s
  AND (od.quantityOrdered < %s OR od.priceEach < %s)
"""

SQL_COUNT_ORDERS_BEYOND_WATERMARK = """
SELECT COUNT(*) AS cnt
FROM orders
WHERE orderDate > %s
"""

# ---------------------------------------------------------------------------
# Result model and builders
# ---------------------------------------------------------------------------


@dataclass
class CheckResult:
    """Outcome of a single validation step."""

    name: str
    passed: bool
    message: str


def _pass(name: str, message: str) -> CheckResult:
    return CheckResult(name=name, passed=True, message=message)


def _fail(name: str, message: str) -> CheckResult:
    return CheckResult(name=name, passed=False, message=message)


# ---------------------------------------------------------------------------
# Shared context loaders
# ---------------------------------------------------------------------------


def _require_watermark_row(conn: Connection, check_name: str) -> Watermark | CheckResult:
    """Return the watermark row or a failed CheckResult."""
    watermark = get_watermark(conn)
    if watermark is None:
        return _fail(
            check_name,
            f"Watermark row is missing; {INIT_HINT}",
        )
    return watermark


def _require_watermark_with_date(conn: Connection, check_name: str) -> Watermark | CheckResult:
    """Return watermark with non-null last_processed_order_date or a failed CheckResult."""
    watermark = _require_watermark_row(conn, check_name)
    if isinstance(watermark, CheckResult):
        return watermark
    if watermark.last_processed_order_date is None:
        return _fail(
            check_name,
            f"last_processed_order_date is NULL; {INIT_HINT}",
        )
    return watermark


def _order_dates_beyond_watermark(
    conn: Connection,
    check_name: str,
) -> tuple[date, date] | CheckResult:
    """Return (watermark_date, max_order_date) for pending-order comparisons."""
    watermark = _require_watermark_with_date(conn, check_name)
    if isinstance(watermark, CheckResult):
        return watermark

    max_order_date = get_max_order_date(conn)
    if max_order_date is None:
        return _fail(check_name, "orders table has no rows.")

    return (
        _to_date(watermark.last_processed_order_date),
        _to_date(max_order_date),
    )


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------


def validate_watermark_table_exists(conn: Connection) -> CheckResult:
    """Check 1: etl_watermark exists and contains classicmodels_sales."""
    row = fetch_one(conn, SQL_WATERMARK_TABLE_EXISTS, (WATERMARK_TABLE,))
    if not row or int(row["table_exists"]) == 0:
        return _fail(
            CHECK_WATERMARK_TABLE,
            f"Table {WATERMARK_TABLE} was not found in the current database.",
        )

    watermark = get_watermark(conn)
    if watermark is None:
        return _fail(
            CHECK_WATERMARK_PIPELINE_ROW,
            f"No row with pipeline_name='{PIPELINE_NAME}' in {WATERMARK_TABLE}.",
        )

    return _pass(
        CHECK_WATERMARK_TABLE,
        f"Found pipeline '{PIPELINE_NAME}' in {WATERMARK_TABLE}.",
    )


def validate_watermark_not_null(conn: Connection) -> CheckResult:
    """Check 2: last_processed_order_date is populated after initialization."""
    watermark = _require_watermark_with_date(conn, CHECK_WATERMARK_DATE)
    if isinstance(watermark, CheckResult):
        return watermark

    return _pass(
        CHECK_WATERMARK_DATE,
        f"last_processed_order_date={watermark.last_processed_order_date}.",
    )


def validate_pending_orders(
    conn: Connection,
    *,
    require_pending: bool,
) -> CheckResult:
    """
    Check 3: pending incremental data relative to the watermark.

    - require_pending=False (after init): baseline coherent or no strict pending requirement
    - require_pending=True (after simulate): MAX(orderDate) > last_processed_order_date
    """
    dates = _order_dates_beyond_watermark(conn, CHECK_PENDING_ORDERS)
    if isinstance(dates, CheckResult):
        return dates

    wm_date, max_date = dates

    if require_pending:
        if max_date > wm_date:
            return _pass(
                CHECK_PENDING_ORDERS,
                (
                    f"Pending ETL data detected: MAX(orderDate)={max_date} > "
                    f"last_processed_order_date={wm_date}."
                ),
            )
        return _fail(
            CHECK_PENDING_ORDERS,
            (
                f"Expected new orders after watermark, but MAX(orderDate)={max_date} "
                f"is not greater than last_processed_order_date={wm_date}."
            ),
        )

    if max_date <= wm_date:
        return _pass(
            CHECK_PENDING_ORDERS,
            (
                f"Baseline coherent: MAX(orderDate)={max_date} <= "
                f"last_processed_order_date={wm_date}."
            ),
        )

    return _pass(
        CHECK_PENDING_ORDERS,
        (
            f"Orders exist beyond watermark (MAX(orderDate)={max_date} > {wm_date}); "
            "run with --require-pending after simulation."
        ),
    )


def validate_orderdetails_integrity(conn: Connection) -> CheckResult:
    """
    Check 4: orders beyond the watermark have orderdetails rows with valid amounts.

    sales_amount rule: quantityOrdered * priceEach requires qty >= 1 and price >= 0.
    """
    watermark = _require_watermark_with_date(conn, CHECK_ORDERDETAILS)
    if isinstance(watermark, CheckResult):
        return watermark

    cutoff = watermark.last_processed_order_date

    orphans = fetch_all(conn, SQL_ORDERS_WITHOUT_ORDERDETAILS, (cutoff,))
    if orphans:
        ids = ", ".join(str(row["orderNumber"]) for row in orphans)
        return _fail(
            CHECK_ORDERDETAILS,
            f"Orders without orderdetails lines: {ids}",
        )

    invalid_lines = fetch_all(
        conn,
        SQL_INVALID_ORDERDETAILS_BEYOND_WATERMARK,
        (cutoff, MIN_VALID_QUANTITY, MIN_VALID_PRICE),
    )
    if invalid_lines:
        return _fail(
            CHECK_ORDERDETAILS,
            "Found orderdetails with non-positive quantity or negative price.",
        )

    row = fetch_one(conn, SQL_COUNT_ORDERS_BEYOND_WATERMARK, (cutoff,))
    count = int(row["cnt"]) if row else 0

    return _pass(
        CHECK_ORDERDETAILS,
        f"All {count} order(s) beyond the watermark have valid orderdetails rows.",
    )


# ---------------------------------------------------------------------------
# Suite runner and CLI output
# ---------------------------------------------------------------------------


def run_all_checks(conn: Connection, *, require_pending: bool = False) -> list[CheckResult]:
    """Run the full validation."""
    return [
        validate_watermark_table_exists(conn),
        validate_watermark_not_null(conn),
        validate_pending_orders(conn, require_pending=require_pending),
        validate_orderdetails_integrity(conn),
    ]


def print_results(results: list[CheckResult]) -> bool:
    """Print human-readable check output; return True if all checks passed."""
    all_passed = True
    for result in results:
        status = "PASS" if result.passed else "FAIL"
        print(f"[{status}] {result.name}: {result.message}")
        if not result.passed:
            all_passed = False
    return all_passed
