from __future__ import annotations

import sys

from common import PIPELINE_NAME, connect, fetch_one_value


CREATE_WATERMARK_TABLE = """
CREATE TABLE IF NOT EXISTS etl_watermark (
    pipeline_name VARCHAR(64) PRIMARY KEY,
    last_processed_order_date DATE,
    last_run_at DATETIME NULL,
    last_run_status VARCHAR(32) NOT NULL
)
"""


def init_watermark() -> None:
    with connect() as connection:
        try:
            with connection.cursor() as cursor:
                cursor.execute(CREATE_WATERMARK_TABLE)
                max_order_date = fetch_one_value(cursor, "SELECT MAX(orderDate) FROM orders")

                if max_order_date is None:
                    raise RuntimeError("orders is empty; cannot initialize a historical baseline.")

                cursor.execute(
                    """
                    INSERT INTO etl_watermark (
                        pipeline_name,
                        last_processed_order_date,
                        last_run_at,
                        last_run_status
                    )
                    VALUES (%s, %s, NULL, 'NEVER_RUN')
                    ON DUPLICATE KEY UPDATE
                        last_processed_order_date = COALESCE(
                            last_processed_order_date,
                            VALUES(last_processed_order_date)
                        ),
                        last_run_status = COALESCE(last_run_status, 'NEVER_RUN')
                    """,
                    (PIPELINE_NAME, max_order_date),
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise

    print(f"Watermark initialized for pipeline={PIPELINE_NAME}.")


def main() -> int:
    try:
        init_watermark()
        return 0
    except Exception as exc:
        print(f"Failed to initialize watermark: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

