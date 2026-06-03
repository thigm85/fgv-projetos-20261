import argparse
import logging
import sys

from db_config import add_db_args, config_from_args, connect, setup_logging


PIPELINE_NAME = "classicmodels_sales"
LOGGER = logging.getLogger(__name__)


def init_watermark(connection) -> None:
    with connection.cursor() as cursor:
        LOGGER.info("Ensuring etl_watermark table exists")
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS etl_watermark (
                pipeline_name VARCHAR(64) NOT NULL PRIMARY KEY,
                last_processed_order_date DATE NOT NULL,
                last_run_at DATETIME NULL,
                last_run_status VARCHAR(32) NOT NULL
            )
            """
        )
        LOGGER.info("Reading current historical baseline from orders")
        cursor.execute("SELECT MAX(orderDate) FROM orders")
        max_order_date = cursor.fetchone()[0]
        if max_order_date is None:
            raise RuntimeError("orders has no rows; cannot initialize last_processed_order_date")

        LOGGER.info("Ensuring watermark row exists for %s", PIPELINE_NAME)
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
                last_processed_order_date = COALESCE(last_processed_order_date, VALUES(last_processed_order_date)),
                last_run_status = COALESCE(last_run_status, 'NEVER_RUN')
            """,
            (PIPELINE_NAME, max_order_date),
        )
    connection.commit()
    LOGGER.info("Watermark committed successfully")
    print(f"Watermark ready for {PIPELINE_NAME}. Baseline orderDate: {max_order_date}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Create and initialize classicmodels ETL watermark.")
    add_db_args(parser)
    args = parser.parse_args()
    setup_logging(args.verbose)

    try:
        config = config_from_args(args)
        connection = connect(config)
        try:
            init_watermark(connection)
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
