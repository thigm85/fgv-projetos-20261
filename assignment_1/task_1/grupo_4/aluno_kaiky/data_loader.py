"""
Script to create the classicmodels database and load sample data from a SQL file.
"""

import mysql.connector
import logging
import os
from mysql.connector import Error
from dotenv import load_dotenv
import sqlparse  

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(os.path.basename(__file__))


def load_config(db_host=os.getenv("DB_HOST")):
    logger.info("Loading configuration from environment variables...")
    config = {
        "host": db_host,
        "user": os.getenv("DB_USER"),
        "password": os.getenv("DB_PASSWORD"),
        "database": os.getenv("DB_NAME"),
    }
    logger.info(f"Configuration loaded: host={config['host']}, database={config['database']}")
    return config


def load_sql_file(filepath):
    logger.info(f"Loading SQL file from path: {filepath}")
    if not os.path.exists(filepath):
        logger.error(f"SQL file not found: {filepath}")
        raise FileNotFoundError(f"SQL file not found: {filepath}")

    with open(filepath, "r", encoding="utf-8") as f:
        sql_content = f.read()
    logger.info(f"SQL file loaded successfully, {len(sql_content)} characters read")
    return sql_content


def execute_sql_script(cursor, sql_script):
    logger.info("Executing SQL script...")
    statements = sqlparse.split(sql_script)  
    executed_count = 0
    try:
        for statement in statements:
            stmt = statement.strip()
            if stmt:
                cursor.execute(stmt)
                executed_count += 1
        logger.info(f"SQL script executed successfully ({executed_count} statements run)")
    except Error as e:
        logger.error(f"Error executing SQL script: {e}")
        raise


def data_loader_pipeline(sql_file, db_host=os.getenv("DB_HOST")):
    config = load_config(db_host)

    try:
        logger.info("Connecting to MySQL server...")
        conn = mysql.connector.connect(
            host=config["host"],
            user=config["user"],
            password=config["password"],
        )
        logger.info("Connection established")

        cursor = conn.cursor()
        logger.info("Creating database if it does not exist...")
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {config['database']};")
        cursor.execute(f"USE {config['database']};")
        logger.info(f"Database '{config['database']}' selected")

        sql_script = load_sql_file(sql_file)
        execute_sql_script(cursor, sql_script)

        conn.commit()
        logger.info("Database successfully loaded and changes committed")

    except Error as e:
        logger.error(f"MySQL error: {e}")

    finally:
        if "cursor" in locals():
            cursor.close()
            logger.info("Cursor closed")
        if "conn" in locals() and conn.is_connected():
            conn.close()
            logger.info("Connection closed")


if __name__ == "__main__":
    data_loader_pipeline("../../data/mysqlsampledatabase.sql")