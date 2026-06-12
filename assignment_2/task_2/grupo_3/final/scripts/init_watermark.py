from db import connect


PIPELINE_NAME = "classicmodels_sales"


def main():
    conn = connect()
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS etl_watermark (
            pipeline_name VARCHAR(64) PRIMARY KEY,
            last_processed_order_date DATE,
            last_run_at DATETIME,
            last_run_status VARCHAR(32) NOT NULL
        )
        """
    )

    cursor.execute("SELECT MAX(orderDate) FROM orders")
    max_order_date = cursor.fetchone()[0]
    if max_order_date is None:
        cursor.close()
        conn.close()
        raise RuntimeError("Nao ha pedidos em orders para inicializar o watermark.")

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

    conn.commit()
    cursor.execute(
        """
        SELECT pipeline_name, last_processed_order_date, last_run_at, last_run_status
        FROM etl_watermark
        WHERE pipeline_name = %s
        """,
        (PIPELINE_NAME,),
    )
    row = cursor.fetchone()

    cursor.close()
    conn.close()

    print("Watermark inicializado:")
    print(f"- pipeline_name: {row[0]}")
    print(f"- last_processed_order_date: {row[1]}")
    print(f"- last_run_at: {row[2]}")
    print(f"- last_run_status: {row[3]}")


if __name__ == "__main__":
    main()
