"""
Initialise (or re-initialise) the etl_watermark table.

Run once against the RDS instance before the first Glue job execution.
Uses ON DUPLICATE KEY UPDATE so it is safe to run multiple times:
- If no row exists → creates it with last_processed_order_date = MAX(orderDate)
- If a row already exists → leaves last_processed_order_date untouched

Usage:
    python init_watermark.py
"""

import os
import sys

import pymysql
from dotenv import load_dotenv

PIPELINE_NAME = "classicmodels_sales"


def _connect():
    load_dotenv()
    host = os.environ["DB_HOST"]
    user = os.environ["DB_USER"]
    password = os.environ["DB_PASSWORD"]
    db = os.getenv("DB_NAME", "classicmodels")
    port = int(os.getenv("DB_PORT", "3306"))
    return pymysql.connect(host=host, port=port, user=user, password=password, database=db)


def main():
    conn = _connect()
    try:
        with conn.cursor() as cur:
            # Create table if not present
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS etl_watermark (
                    pipeline_name              VARCHAR(64)  NOT NULL,
                    last_processed_order_date  DATE,
                    last_run_at                DATETIME,
                    last_run_status            VARCHAR(32)  NOT NULL,
                    PRIMARY KEY (pipeline_name)
                )
                """
            )

            cur.execute("SELECT MAX(orderDate) FROM orders")
            max_order_date = cur.fetchone()[0]
            if max_order_date is None:
                raise RuntimeError("No orders in the database — cannot initialise watermark.")

            # Idempotent upsert: never overwrite an existing watermark date
            cur.execute(
                """
                INSERT INTO etl_watermark
                    (pipeline_name, last_processed_order_date, last_run_at, last_run_status)
                VALUES (%s, %s, NULL, 'NEVER_RUN')
                ON DUPLICATE KEY UPDATE
                    last_processed_order_date =
                        COALESCE(last_processed_order_date, VALUES(last_processed_order_date)),
                    last_run_status = COALESCE(last_run_status, 'NEVER_RUN')
                """,
                (PIPELINE_NAME, max_order_date),
            )
            conn.commit()

            cur.execute(
                """
                SELECT pipeline_name, last_processed_order_date,
                       last_run_at, last_run_status
                FROM etl_watermark
                WHERE pipeline_name = %s
                """,
                (PIPELINE_NAME,),
            )
            row = cur.fetchone()

        print("Watermark initialised:")
        print(f"  pipeline_name             : {row[0]}")
        print(f"  last_processed_order_date : {row[1]}")
        print(f"  last_run_at               : {row[2]}")
        print(f"  last_run_status           : {row[3]}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
