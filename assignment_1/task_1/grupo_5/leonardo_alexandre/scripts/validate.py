import mysql.connector
import logging
import boto3
from ..config.config import *

logging.basicConfig(level=logging.INFO)

def get_endpoint():
    rds = boto3.client('rds', region_name=AWS_REGION)
    response = rds.describe_db_instances(DBInstanceIdentifier=DB_INSTANCE_ID)
    return response['DBInstances'][0]['Endpoint']['Address']

def validate():
    endpoint = get_endpoint()

    conn = mysql.connector.connect(
        host=endpoint,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        port=DB_PORT
    )

    cursor = conn.cursor()

    cursor.execute("SHOW TABLES")
    tables = cursor.fetchall()

    for table in tables:
        name = table[0]

        cursor.execute(f"SELECT COUNT(*) FROM {name}")
        count = cursor.fetchone()[0]

        logging.info(f"{name}: {count} registros")

    cursor.close()
    conn.close()

if __name__ == "__main__":
    validate()