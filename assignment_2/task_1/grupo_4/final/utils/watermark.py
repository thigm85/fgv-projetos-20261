"""
Create and read the etl_watermark control table on RDS.

Public API
----------
- initialize_watermark  — idempotent setup + seed row
- drop_watermark_table  — remove etl_watermark (cleanup / teardown)
- get_watermark         — read pipeline row
- get_max_order_date    — OLTP high-water mark for orders.orderDate
"""

from __future__ import annotations

from datetime import date
from typing import Any

from pymysql.connections import Connection

from src.models import Watermark
from utils.config import PIPELINE_NAME, STATUS_NEVER_RUN, WATERMARK_TABLE
from utils.database import execute, fetch_one

# ---------------------------------------------------------------------------
# SQL — schema 
# ---------------------------------------------------------------------------

DDL_DROP_WATERMARK_TABLE = f"DROP TABLE IF EXISTS {WATERMARK_TABLE}"

DDL_CREATE_WATERMARK_TABLE = f"""
CREATE TABLE IF NOT EXISTS {WATERMARK_TABLE} (
    pipeline_name VARCHAR(64) NOT NULL PRIMARY KEY,
    last_processed_order_date DATE NULL,
    last_run_at DATETIME NULL,
    last_run_status VARCHAR(32) NOT NULL
)
"""

# Inserts only when pipeline_name is missing; baseline = MAX(orders.orderDate).
# Placeholders: pipeline_name, last_run_status, pipeline_name (NOT EXISTS).
DML_SEED_WATERMARK_IF_ABSENT = f"""
INSERT INTO {WATERMARK_TABLE} (
    pipeline_name,
    last_processed_order_date,
    last_run_at,
    last_run_status
)
SELECT
    %s,
    (SELECT MAX(orderDate) FROM orders),
    NULL,
    %s
FROM DUAL
WHERE NOT EXISTS (
    SELECT 1
    FROM {WATERMARK_TABLE}
    WHERE pipeline_name = %s
)
"""

# ---------------------------------------------------------------------------
# SQL — reads
# ---------------------------------------------------------------------------

SQL_SELECT_WATERMARK_BY_PIPELINE = f"""
SELECT
    pipeline_name,
    last_processed_order_date,
    last_run_at,
    last_run_status
FROM {WATERMARK_TABLE}
WHERE pipeline_name = %s
"""

SQL_SELECT_MAX_ORDER_DATE = """
SELECT MAX(orderDate) AS max_order_date
FROM orders
"""

# ---------------------------------------------------------------------------
# Row mapping helpers
# ---------------------------------------------------------------------------


def _to_date(value: Any) -> date | None:
    """Normalize MySQL DATE/DATETIME values to datetime.date."""
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if hasattr(value, "date"):
        return value.date()
    return value


def _row_to_watermark(row: dict) -> Watermark:
    """Build a Watermark dataclass from a SELECT row."""
    return Watermark(
        pipeline_name=row["pipeline_name"],
        last_processed_order_date=_to_date(row["last_processed_order_date"]),
        last_run_at=row["last_run_at"],
        last_run_status=row["last_run_status"],
    )


# ---------------------------------------------------------------------------
# Write path — table creation and initial seed
# ---------------------------------------------------------------------------


def create_watermark_table(conn: Connection) -> None:
    """Create etl_watermark if it does not exist."""
    execute(conn, DDL_CREATE_WATERMARK_TABLE)
    conn.commit()


def drop_watermark_table(conn: Connection) -> None:
    """Drop etl_watermark. Does not delete simulated rows in orders/orderdetails."""
    execute(conn, DDL_DROP_WATERMARK_TABLE)
    conn.commit()


def initialize_watermark(conn: Connection) -> Watermark | None:
    """
    Ensure the control table exists and seed classicmodels_sales when absent.

    Does not update an existing row (Task 2 Glue job owns watermark updates).
    Returns the watermark row after initialization.
    """
    create_watermark_table(conn)
    execute(
        conn,
        DML_SEED_WATERMARK_IF_ABSENT,
        (PIPELINE_NAME, STATUS_NEVER_RUN, PIPELINE_NAME),
    )
    conn.commit()
    return get_watermark(conn)


# ---------------------------------------------------------------------------
# Read path — watermark metadata and OLTP baseline
# ---------------------------------------------------------------------------


def get_watermark(conn: Connection) -> Watermark | None:
    """Fetch the watermark row for classicmodels_sales, or None if missing."""
    row = fetch_one(conn, SQL_SELECT_WATERMARK_BY_PIPELINE, (PIPELINE_NAME,))
    if row is None:
        return None
    return _row_to_watermark(row)


def get_max_order_date(conn: Connection) -> date | None:
    """Return MAX(orders.orderDate) in the database."""
    row = fetch_one(conn, SQL_SELECT_MAX_ORDER_DATE)
    if not row:
        return None
    return _to_date(row["max_order_date"])
