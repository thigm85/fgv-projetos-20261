from db import get_connection
from watermark import get_watermark, WATERMARK_TABLE, PIPELINE_NAME


def validate_incremental_source():
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) AS cnt FROM information_schema.tables "
                "WHERE table_schema = DATABASE() AND table_name = %s",
                (WATERMARK_TABLE,),
            )
            if cursor.fetchone()["cnt"] == 0:
                print(f"Missing table: {WATERMARK_TABLE}")
                raise SystemExit(1)

            watermark = get_watermark(cursor)
            if watermark is None:
                print(f"Missing watermark row for pipeline {PIPELINE_NAME}")
                raise SystemExit(1)
            if watermark["last_processed_order_date"] is None:
                print("Watermark row exists, but last_processed_order_date is NULL")
                raise SystemExit(1)

            cursor.execute("SELECT MAX(orderDate) AS max_date FROM orders")
            max_order_date = cursor.fetchone()["max_date"]
            if max_order_date is None:
                print("orders table is empty or unavailable")
                raise SystemExit(1)

            pending_query = (
                "SELECT o.orderNumber, o.orderDate, COUNT(d.orderNumber) AS detail_count "
                "FROM orders o "
                "LEFT JOIN orderdetails d ON o.orderNumber = d.orderNumber "
                "WHERE o.orderDate > %s "
                "GROUP BY o.orderNumber, o.orderDate"
            )
            cursor.execute(pending_query, (watermark["last_processed_order_date"],))
            pending_orders = cursor.fetchall()

            print(f"Watermark last_processed_order_date: {watermark['last_processed_order_date']}")
            print(f"Max orders.orderDate: {max_order_date}")
            print(f"Pending orders after watermark: {len(pending_orders)}")

            if pending_orders:
                bad_orders = [row for row in pending_orders if row["detail_count"] == 0]
                if bad_orders:
                    print("Found orders after watermark without orderdetails:")
                    for bad in bad_orders:
                        print(f" orderNumber={bad['orderNumber']} orderDate={bad['orderDate']}")
                    raise SystemExit(1)

            print("Incremental source validation passed.")
