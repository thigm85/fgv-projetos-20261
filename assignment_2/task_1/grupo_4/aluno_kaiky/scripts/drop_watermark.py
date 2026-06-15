#!/usr/bin/env python3
"""
Drop the etl_watermark control table from classicmodels.

Does NOT remove simulated orders in orders / orderdetails.

Usage:
    python scripts/drop_watermark.py
"""

from __future__ import annotations
from _bootstrap import setup
from utils.config import load_settings
from utils.tasks import task_drop_watermark

setup(__file__)

def main() -> int:
    return task_drop_watermark(load_settings())


if __name__ == "__main__":
    raise SystemExit(main())
