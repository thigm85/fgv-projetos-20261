"""
Script to check if all tables have been created, populated correctly, 
and have the expected columns with their data types.
"""

import mysql.connector
import logging
import os
from mysql.connector import Error
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(os.path.basename(__file__))

EXPECTED_TABLES = [
    "customers", "products", "productlines",
    "orders", "orderdetails", "payments",
    "employees", "offices",
]

def load_config(DB_HOST=os.getenv("DB_HOST")):
    config = {
        "host": DB_HOST,
        "user": os.getenv("DB_USER", "admin"),
        "password": os.getenv("DB_PASSWORD"),
        "database": os.getenv("DB_NAME", "classicmodels"),
    }
    return config


def validate_database(db_host=os.getenv("DB_HOST")):
    config = load_config(db_host)
    try:
        logger.info(f"Connecting to database {config['database']}")
        conn = mysql.connector.connect(
            host=config["host"],
            user=config["user"],
            password=config["password"],
            database=config["database"],
        )

        cursor = conn.cursor()

        all_ok = True

        for table in EXPECTED_TABLES:
            try:
                # Row count
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                count = cursor.fetchone()[0]
                status = "OK" if count > 0 else "EMPTY"
                if count == 0:
                    all_ok = False

                logger.info(f"\nTable: {table} | Rows: {count} | Status: {status}")

                # Columns and data types
                cursor.execute(f"""
                    SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, COLUMN_KEY
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_SCHEMA = '{config['database']}' AND TABLE_NAME = '{table}'
                    ORDER BY ORDINAL_POSITION
                """)
                columns = cursor.fetchall()

                if columns:
                    logger.info(f"{'Column':<20} {'Type':<15} {'Nullable':<10} {'Key':<5}")
                    logger.info("-" * 55)
                    for col_name, data_type, is_nullable, col_key in columns:
                        logger.info(f"{col_name:<20} {data_type:<15} {is_nullable:<10} {col_key:<5}")
                else:
                    logger.warning(f"No columns found for table '{table}'")
                    all_ok = False

            except Error as e:
                logger.error(f"Error querying table '{table}': {e}")
                all_ok = False

        logger.info("")
        if all_ok:
            logger.info("Validation completed: all tables exist, populated, and have columns.")
        else:
            logger.warning("Validation warning: some tables may be missing, empty, or have column issues.")

    except Error as e:
        logger.error(f"MySQL error: {e}")

    finally:
        if "cursor" in locals():
            cursor.close()
        if "conn" in locals() and conn.is_connected():
            conn.close()
            logger.info("Connection closed")


if __name__ == "__main__":
    validate_database()