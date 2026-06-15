"""
One function per script in scripts/ — shared logic so CLIs stay thin.

Each function returns a process exit code (0 = success).
main.py calls these same functions in sequence; there is no extra "demo" task here.
"""

from __future__ import annotations

from utils.cli import (
    connection_target,
    print_simulation_summary,
    print_validation_footer,
    print_watermark_init_result,
)
from utils.config import WATERMARK_TABLE, Settings, load_settings
from utils.database import db_session
from utils.order_simulator import (
    DEFAULT_LINES_PER_ORDER,
    MIN_ORDER_COUNT,
    simulate_orders,
)
from utils.validator import print_results, run_all_checks
from utils.watermark import drop_watermark_table, get_max_order_date, initialize_watermark


def task_init_watermark(settings: Settings | None = None) -> int:
    """Create etl_watermark and seed classicmodels_sales when missing."""
    settings = settings or load_settings()
    print(f"Connecting to {connection_target(settings)} ...")

    with db_session(settings) as conn:
        watermark = initialize_watermark(conn)
        max_order_date = get_max_order_date(conn)

    return print_watermark_init_result(watermark, max_order_date)


def task_simulate_orders(
    settings: Settings | None = None,
    *,
    count: int,
    seed: int | None = None,
    lines_per_order: int = DEFAULT_LINES_PER_ORDER,
) -> int:
    """Insert simulated orders and orderdetails beyond the watermark."""
    settings = settings or load_settings()

    if count < MIN_ORDER_COUNT:
        print(f"ERROR: count must be >= {MIN_ORDER_COUNT}.")
        return 1

    print(f"Simulating {count} order(s) on {connection_target(settings)} ...")

    with db_session(settings) as conn:
        summary = simulate_orders(
            conn,
            count=count,
            seed=seed,
            lines_per_order=max(1, lines_per_order),
        )

    print_simulation_summary(summary)
    return 0


def task_validate_source(
    settings: Settings | None = None,
    *,
    require_pending: bool = False,
) -> int:
    """Run all incremental-source checks."""
    settings = settings or load_settings()
    print(f"Validating incremental source on {connection_target(settings)} ...")

    with db_session(settings) as conn:
        results = run_all_checks(conn, require_pending=require_pending)

    print()
    return print_validation_footer(print_results(results))


def task_drop_watermark(settings: Settings | None = None) -> int:
    """Drop the etl_watermark control table (optional teardown)."""
    settings = settings or load_settings()
    print(f"Dropping {WATERMARK_TABLE} on {connection_target(settings)} ...")

    with db_session(settings) as conn:
        drop_watermark_table(conn)

    print(f"Table {WATERMARK_TABLE} dropped.")
    return 0
