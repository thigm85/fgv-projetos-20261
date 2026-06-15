from utils.watermark import (
    PIPELINE_NAME,
    get_watermark,
    get_max_order_date
)


def validate_watermark_table(conn):

    cursor = conn.cursor()

    cursor.execute("""
    SHOW TABLES LIKE 'etl_watermark'
    """)

    return cursor.fetchone() is not None


def validate_pipeline_record(conn):

    cursor = conn.cursor()

    cursor.execute("""
    SELECT *
    FROM etl_watermark
    WHERE pipeline_name=%s
    """, (PIPELINE_NAME,))

    return cursor.fetchone() is not None


def validate_pending_orders(conn):

    watermark = get_watermark(conn)

    max_order_date = get_max_order_date(conn)

    return max_order_date > watermark


def validate_orderdetails(conn):

    watermark = get_watermark(conn)

    cursor = conn.cursor()

    cursor.execute("""
    SELECT COUNT(*)
    FROM orders o
    LEFT JOIN orderdetails od
        ON o.orderNumber = od.orderNumber
    WHERE o.orderDate > %s
      AND od.orderNumber IS NULL
    """, (watermark,))

    return cursor.fetchone()[0] == 0


def run_all_checks(conn):

    results = []

    results.append(
        ("Watermark table exists",
         validate_watermark_table(conn))
    )

    results.append(
        ("Pipeline record exists",
         validate_pipeline_record(conn))
    )

    results.append(
        ("Pending incremental data",
         validate_pending_orders(conn))
    )

    results.append(
        ("Orderdetails integrity",
         validate_orderdetails(conn))
    )

    return results