from db import get_connection

PIPELINE_NAME = "classicmodels_sales"
WATERMARK_TABLE = "etl_watermark"


def create_watermark_table(cursor):
    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {WATERMARK_TABLE} (
            pipeline_name VARCHAR(64) PRIMARY KEY,
            last_processed_order_date DATE,
            last_run_at DATETIME,
            last_run_status VARCHAR(32)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """
    )


def get_orders_max_date(cursor):
    cursor.execute("SELECT MAX(orderDate) AS max_date FROM orders")
    row = cursor.fetchone()
    return row["max_date"] if row else None


def get_watermark(cursor):
    cursor.execute(
        f"SELECT pipeline_name, last_processed_order_date, last_run_at, last_run_status"
        f" FROM {WATERMARK_TABLE} WHERE pipeline_name = %s",
        (PIPELINE_NAME,),
    )
    return cursor.fetchone()


def init_watermark():
    with get_connection() as conn:
        with conn.cursor() as cursor:
            create_watermark_table(cursor)
            current_max = get_orders_max_date(cursor)
            if current_max is None:
                raise SystemExit("orders table is empty or does not exist.")

            watermark = get_watermark(cursor)
            if watermark is None:
                cursor.execute(
                    f"INSERT INTO {WATERMARK_TABLE} "
                    "(pipeline_name, last_processed_order_date, last_run_at, last_run_status) "
                    "VALUES (%s, %s, NULL, 'NEVER_RUN')",
                    (PIPELINE_NAME, current_max),
                )
                conn.commit()
                print(f"Inserted watermark row for {PIPELINE_NAME} with last_processed_order_date={current_max}.")
            elif watermark["last_processed_order_date"] is None:
                cursor.execute(
                    f"UPDATE {WATERMARK_TABLE} SET last_processed_order_date = %s, last_run_status = 'NEVER_RUN' "
                    "WHERE pipeline_name = %s",
                    (current_max, PIPELINE_NAME),
                )
                conn.commit()
                print(f"Updated watermark row for {PIPELINE_NAME} with last_processed_order_date={current_max}.")
            else:
                print(
                    f"Watermark row already exists for {PIPELINE_NAME} "
                    f"with last_processed_order_date={watermark['last_processed_order_date']}."
                )
