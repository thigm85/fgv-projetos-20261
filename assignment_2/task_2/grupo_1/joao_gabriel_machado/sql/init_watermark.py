import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

load_dotenv()

DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')
DB_HOST = os.getenv('DB_HOST')
DB_NAME = 'classicmodels'
DB_PORT = "3306"

def init_watermark():
    connection_string = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    engine = create_engine(connection_string)

    create_table_sql = """
        CREATE TABLE IF NOT EXISTS etl_watermark (
            pipeline_name VARCHAR(64) PRIMARY KEY,
            last_processed_order_date DATE,
            last_run_at DATETIME,
            last_run_status VARCHAR(32)
        );
    """

    upsert_watermark_sql = """
        INSERT INTO etl_watermark (pipeline_name, last_processed_order_date, last_run_status)
        SELECT 
            'classicmodels_sales', 
            MAX(orderDate), 
            'INITIALIZED'
        FROM orders
        ON DUPLICATE KEY UPDATE 
            last_processed_order_date = (SELECT MAX(orderDate) FROM orders);
    """

    try:
        with engine.begin() as connection:
            connection.execute(text(create_table_sql))
            print("Table 'etl_watermark' created or verified.")

            connection.execute(text(upsert_watermark_sql))
            print("Watermark record inserted/updated for 'classicmodels_sales'.")

            result = connection.execute(text("SELECT * FROM etl_watermark;")).fetchone()
            print(f"Current watermark state: {result}")

    except SQLAlchemyError as e:
        print(f"Database error occurred: {e}")

if __name__ == "__main__":
    init_watermark()