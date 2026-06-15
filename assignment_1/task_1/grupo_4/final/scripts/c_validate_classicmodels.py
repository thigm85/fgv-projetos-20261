"""Verify classicmodels tables exist and are non-empty."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from classicmodels_rds.config import load_settings  # noqa: E402
from classicmodels_rds.mysql_io import connect_with_retries, validate_classicmodels  # noqa: E402


def main() -> None:
    settings = load_settings()
    conn = connect_with_retries(settings)
    try:
        ok = validate_classicmodels(conn, settings)
    finally:
        conn.close()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
