#!/usr/bin/env python3
"""
Optional end-to-end runner: runs the four README steps in sequence.

This file only orchestrates; each step reuses the same code as scripts/*.py
via utils/tasks.py (init -> validate -> simulate -> validate --require-pending).

Usage:
    python main.py
    python main.py --count 10 --seed 42
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from utils.config import load_settings
from utils.tasks import (
    task_init_watermark,
    task_simulate_orders,
    task_validate_source,
    task_drop_watermark
)

def main() -> int:
    settings = load_settings()
    parser = argparse.ArgumentParser(
        description="Run init -> validate -> simulate -> validate (full README flow)."
    )
    parser.add_argument(
        "--count",
        type=int,
        default=None,
        help=f"Orders to simulate (default: {settings.default_simulate_count}).",
    )
    parser.add_argument("--seed", type=int, default=None, help="RNG seed.")
    args = parser.parse_args()
    count = args.count if args.count is not None else settings.default_simulate_count

    print("Step 1/4: init_watermark")
    if task_init_watermark(settings) != 0:
        return 1

    print("\nStep 2/4: validate_incremental_source (baseline)")
    if task_validate_source(settings, require_pending=False) != 0:
        return 1

    print(f"\nStep 3/4: simulate_new_orders (count={count})")
    if task_simulate_orders(settings, count=count, seed=args.seed) != 0:
        return 1

    print("\nStep 4/4: validate_incremental_source (--require-pending)")
    if task_validate_source(settings, require_pending=True) != 0:
        return 1

    print("\nFull flow completed successfully.")

    # Optional teardown — drops only etl_watermark (not simulated orders):
    # if task_drop_watermark(settings) != 0:
    #     return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
