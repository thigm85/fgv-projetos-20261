#!/usr/bin/env python3
"""
Simulate new orders in classicmodels for incremental ETL demos.

Usage:
    python scripts/simulate_new_orders.py --count 5
    python scripts/simulate_new_orders.py --count 10 --seed 42
"""

from __future__ import annotations

import argparse

from _bootstrap import setup

setup(__file__)

from utils.config import load_settings
from utils.order_simulator import DEFAULT_LINES_PER_ORDER
from utils.tasks import task_simulate_orders


def _build_parser(default_count: int) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Insert simulated orders and orderdetails into classicmodels."
    )
    parser.add_argument(
        "--count",
        type=int,
        default=default_count,
        help=f"Number of orders to create (default: {default_count}).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Optional RNG seed for reproducible demos.",
    )
    parser.add_argument(
        "--lines-per-order",
        type=int,
        default=DEFAULT_LINES_PER_ORDER,
        help=(
            "Minimum orderdetails lines per simulated order "
            f"(default: {DEFAULT_LINES_PER_ORDER})."
        ),
    )
    return parser


def main() -> int:
    settings = load_settings()
    args = _build_parser(settings.default_simulate_count).parse_args()
    return task_simulate_orders(
        settings,
        count=args.count,
        seed=args.seed,
        lines_per_order=args.lines_per_order,
    )


if __name__ == "__main__":
    raise SystemExit(main())
