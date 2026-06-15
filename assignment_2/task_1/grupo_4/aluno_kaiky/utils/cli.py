"""Human-readable CLI output shared by scripts and main.py."""

from __future__ import annotations

from src.models import SimulationSummary, Watermark
from utils.config import PIPELINE_NAME, Settings


def connection_target(settings: Settings) -> str:
    """Short label for logs: host/database."""
    return f"{settings.db_host}/{settings.db_name}"


def print_watermark_init_result(
    watermark: Watermark | None,
    max_order_date,
) -> int:
    """
    Print init_watermark summary.
    Returns process exit code (0 = success).
    """
    if watermark is None:
        print("ERROR: watermark row was not created.")
        return 1

    print("Watermark initialization completed.")
    print(f"  pipeline_name              : {watermark.pipeline_name}")
    print(f"  last_processed_order_date  : {watermark.last_processed_order_date}")
    print(f"  last_run_status            : {watermark.last_run_status}")
    print(f"  MAX(orders.orderDate)      : {max_order_date}")

    if watermark.pipeline_name != PIPELINE_NAME:
        print("ERROR: unexpected pipeline_name.")
        return 1

    return 0


def print_simulation_summary(summary: SimulationSummary) -> None:
    """Print the assignment-required simulation recap."""
    print("\n=== Simulation summary ===")
    print(f"Order IDs created     : {summary.order_numbers}")
    print(f"Order date range      : {summary.min_order_date} .. {summary.max_order_date}")
    print(f"orderdetails rows     : {summary.orderdetails_rows}")
    print("\nLine items (sales_amount = quantity * priceEach):")
    for item in summary.line_items:
        print(
            f"  order={item.order_number} line={item.order_line_number} "
            f"product={item.product_code} qty={item.quantity_ordered} "
            f"price={item.price_each} sales_amount={item.sales_amount}"
        )
    print("\nNote: etl_watermark was NOT updated (by design).")


def print_validation_footer(all_passed: bool) -> int:
    """Print final validation message. Returns exit code."""
    if all_passed:
        print("All checks passed.")
        return 0
    print("One or more checks failed.")
    return 1
