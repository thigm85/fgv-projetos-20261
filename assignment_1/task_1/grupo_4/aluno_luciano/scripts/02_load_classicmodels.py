"""Load mysqlsampledatabase.sql into RDS."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from classicmodels_rds.config import load_settings
from classicmodels_rds.mysql_io import connect_with_retries, run_sql_file


def main() -> None:
    settings = load_settings()
    if not settings.db_password:
        print("Set DB_PASSWORD or RDS_MASTER_PASSWORD in .env.", file=sys.stderr)
        sys.exit(1)

    conn = connect_with_retries(settings)
    try:
        run_sql_file(conn, settings.sql_file_path)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
