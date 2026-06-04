from __future__ import annotations

import sys

from common import PIPELINE_NAME, connect, fetch_one_value


CREATE_WATERMARK_TABLE = """
CREATE TABLE IF NOT EXISTS etl_watermark (
    pipeline_name VARCHAR(64) PRIMARY KEY,
    last_processed_order_date DATE,
    last_run_at DATETIME,
    last_run_status VARCHAR(32)
)
"""


def init_watermark() -> None:
    with connect() as connection:
        try:
            with connection.cursor() as cursor:
                cursor.execute(CREATE_WATERMARK_TABLE)
                max_order_date = fetch_one_value(cursor, "SELECT MAX(orderDate) FROM orders")

                if max_order_date is None:
                    raise RuntimeError("A tabela orders está vazia; não há baseline histórico para inicializar.")

                cursor.execute(
                    """
                    INSERT INTO etl_watermark (
                        pipeline_name,
                        last_processed_order_date,
                        last_run_at,
                        last_run_status
                    )
                    VALUES (%s, %s, UTC_TIMESTAMP(), 'NEVER_RUN')
                    ON DUPLICATE KEY UPDATE
                        last_processed_order_date = IF(
                            last_processed_order_date IS NULL,
                            VALUES(last_processed_order_date),
                            last_processed_order_date
                        ),
                        last_run_status = IFNULL(last_run_status, 'NEVER_RUN')
                    """,
                    (PIPELINE_NAME, max_order_date),
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise

    print(f"Watermark inicializado para pipeline={PIPELINE_NAME}.")


def main() -> int:
    try:
        init_watermark()
        return 0
    except Exception as exc:
        print(f"Erro ao inicializar watermark: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
