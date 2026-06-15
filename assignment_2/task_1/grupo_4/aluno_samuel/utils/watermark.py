PIPELINE_NAME = "classicmodels_sales"


def create_watermark_table(conn):

    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS etl_watermark (
        pipeline_name VARCHAR(64) PRIMARY KEY,
        last_processed_order_date DATE,
        last_run_at DATETIME,
        last_run_status VARCHAR(32)
    )
    """)

    conn.commit()


def initialize_watermark(conn):

    cursor = conn.cursor()

    create_watermark_table(conn)

    cursor.execute("""
    SELECT MAX(orderDate)
    FROM orders
    """)

    max_date = cursor.fetchone()[0]

    cursor.execute("""
    INSERT INTO etl_watermark (
        pipeline_name,
        last_processed_order_date,
        last_run_at,
        last_run_status
    )
    VALUES (%s,%s,NULL,'NEVER_RUN')
    ON DUPLICATE KEY UPDATE
        pipeline_name = pipeline_name
    """, (PIPELINE_NAME, max_date))

    conn.commit()

    return max_date


def get_watermark(conn):

    cursor = conn.cursor()

    cursor.execute("""
    SELECT last_processed_order_date
    FROM etl_watermark
    WHERE pipeline_name=%s
    """, (PIPELINE_NAME,))

    row = cursor.fetchone()

    if row is None:
        return None

    return row[0]


def get_max_order_date(conn):

    cursor = conn.cursor()

    cursor.execute("""
    SELECT MAX(orderDate)
    FROM orders
    """)

    return cursor.fetchone()[0]