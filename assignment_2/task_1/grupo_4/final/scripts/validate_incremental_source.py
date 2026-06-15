#!/usr/bin/env python3
"""
Validate that the OLTP source is ready for incremental Glue ETL (Task 2).

Exit code 0 only when all checks pass.

Usage:
    python scripts/validate_incremental_source.py
    python scripts/validate_incremental_source.py --require-pending
"""

from __future__ import annotations

import argparse

from _bootstrap import setup

setup(__file__)

from utils.config import load_settings
from utils.tasks import task_validate_source


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate etl_watermark and incremental order readiness."
    )
    parser.add_argument(
        "--require-pending",
        action="store_true",
        help=(
            "Require MAX(orders.orderDate) > last_processed_order_date "
            "(use after simulate_new_orders.py)."
        ),
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    return task_validate_source(
        load_settings(),
        require_pending=args.require_pending,
    )


if __name__ == "__main__":
    raise SystemExit(main())
