"""Domain model for etl_watermark rows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

@dataclass(frozen=True)
class Watermark:
    """Row from etl_watermark for pipeline classicmodels_sales."""

    pipeline_name: str
    last_processed_order_date: date | None
    last_run_at: datetime | None
    last_run_status: str


@dataclass(frozen=True)
class SimulatedLineItem:
    """Single orderdetails row created by the simulator."""

    order_number: int
    product_code: str
    quantity_ordered: int
    price_each: Decimal
    order_line_number: int

    @property
    def sales_amount(self) -> Decimal:
        """Star-schema rule: sales_amount = quantity * unit price."""
        return Decimal(self.quantity_ordered) * self.price_each


@dataclass(frozen=True)
class SimulationSummary:
    """Aggregated result returned by simulate_orders and printed by the CLI script."""

    order_numbers: list[int]
    min_order_date: date
    max_order_date: date
    orderdetails_rows: int
    line_items: list[SimulatedLineItem]