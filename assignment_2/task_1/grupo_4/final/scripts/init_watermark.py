#!/usr/bin/env python3
"""
Idempotent initialization of etl_watermark on classicmodels (RDS).

Usage (from project root):
    python scripts/init_watermark.py
"""

from __future__ import annotations

from _bootstrap import setup

setup(__file__)

from utils.config import load_settings
from utils.tasks import task_init_watermark


def main() -> int:
    return task_init_watermark(load_settings())


if __name__ == "__main__":
    raise SystemExit(main())
