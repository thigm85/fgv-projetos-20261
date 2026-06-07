import os
import sys
import pymysql

RDS_HOST = os.environ["RDS_HOST"]
RDS_PORT = int(os.environ.get("RDS_PORT", 3306))
RDS_USER = os.environ["RDS_USER"]
RDS_PASSWORD = os.environ["RDS_PASSWORD"]
RDS_DB = os.environ.get("RDS_DB", "classicmodels")


def main():
    conn = pymysql.connect(
        host=RDS_HOST,
        port=RDS_PORT,
        user=RDS_USER,
        password=RDS_PASSWORD,
        database=RDS_DB,
        autocommit=False,
        charset="utf8mb4",
    )

    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS etl_watermark (
                pipeline_name             VARCHAR(64) NOT NULL,
                last_processed_order_date DATE,
                last_run_at               DATETIME,
                last_run_status           VARCHAR(32),
                PRIMARY KEY (pipeline_name)
            )
            """
        )

        cur.execute(
            """
            INSERT INTO etl_watermark (pipeline_name, last_processed_order_date, last_run_at, last_run_status)
            SELECT
                'classicmodels_sales',
                MAX(orderDate),
                NOW(),
                'NEVER_RUN'
            FROM orders
            ON DUPLICATE KEY UPDATE
                last_processed_order_date = VALUES(last_processed_order_date)
            """
        )

        cur.execute(
            "SELECT last_processed_order_date, last_run_status FROM etl_watermark WHERE pipeline_name = 'classicmodels_sales'"
        )
        row = cur.fetchone()

    conn.commit()
    conn.close()

    print("etl_watermark inicializado com sucesso.")
    print(f"  last_processed_order_date : {row[0]}")
    print(f"  last_run_status           : {row[1]}")


if __name__ == "__main__":
    main()
