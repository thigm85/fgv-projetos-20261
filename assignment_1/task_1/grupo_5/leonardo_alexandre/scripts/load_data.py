import mysql.connector
import logging
import boto3
import sqlparse
from ..config.config import *

logging.basicConfig(level=logging.INFO)

def get_endpoint():
    rds = boto3.client('rds', region_name=AWS_REGION)
    response = rds.describe_db_instances(DBInstanceIdentifier=DB_INSTANCE_ID)
    return response['DBInstances'][0]['Endpoint']['Address']

def load():
    endpoint = get_endpoint()

    conn = mysql.connector.connect(
        host=endpoint,
        user=DB_USER,
        password=DB_PASSWORD,
        port=DB_PORT
    )

    cursor = conn.cursor(buffered=True)

    cursor.execute(f"CREATE DATABASE IF NOT EXISTS {DB_NAME}")
    cursor.execute(f"USE {DB_NAME}")

    logging.info("Carregando SQL...")

    with open("data/mysqlsampledatabase.sql", "r", encoding="utf-8") as f:
        sql = f.read()

    statements = sqlparse.split(sql)

    for statement in statements:
        if statement.strip():
            cursor.execute(statement)

    conn.commit()
    cursor.close()
    conn.close()

    logging.info("Carga finalizada!")

if __name__ == "__main__":
    load()