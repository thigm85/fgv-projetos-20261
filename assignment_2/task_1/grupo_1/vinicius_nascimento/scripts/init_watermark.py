from db import get_connection


PIPELINE_NAME = "classicmodels_sales"


def main():
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS etl_watermark (
                pipeline_name VARCHAR(64) PRIMARY KEY,
                last_processed_order_date DATE,
                last_run_at DATETIME,
                last_run_status VARCHAR(32)
            )
        """)

        cursor.execute("SELECT MAX(orderDate) FROM orders")
        max_order_date = cursor.fetchone()[0]

        if max_order_date is None:
            raise RuntimeError("A tabela orders está vazia. Não foi possível inicializar o watermark.")

        cursor.execute("""
            INSERT INTO etl_watermark (
                pipeline_name,
                last_processed_order_date,
                last_run_at,
                last_run_status
            )
            VALUES (%s, %s, NULL, 'NEVER_RUN')
            ON DUPLICATE KEY UPDATE
                last_processed_order_date =
                    COALESCE(last_processed_order_date, VALUES(last_processed_order_date)),
                last_run_status =
                    COALESCE(last_run_status, VALUES(last_run_status))
        """, (PIPELINE_NAME, max_order_date))

        conn.commit()

        print("Watermark inicializado com sucesso.")
        print(f"pipeline_name: {PIPELINE_NAME}")
        print(f"last_processed_order_date: {max_order_date}")

    except Exception:
        conn.rollback()
        raise

    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    main()