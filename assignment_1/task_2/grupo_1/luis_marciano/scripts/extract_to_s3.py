import pymysql
import pandas as pd
import boto3
from io import StringIO

def extract_to_s3():
    # Read config
    config = {}
    with open('rds_config.txt', 'r') as f:
        for line in f:
            key, value = line.strip().split('=')
            config[key] = value

    # Connect to RDS
    connection = pymysql.connect(
        host=config['endpoint'],
        port=int(config['port']),
        user=config['username'],
        password=config['password'],
        database=config['database']
    )

    # Tables to extract
    tables = {
        'customers': 'SELECT * FROM customers',
        'products': 'SELECT * FROM products',
        'productlines': 'SELECT * FROM productlines',
        'orders': 'SELECT * FROM orders',
        'orderdetails': 'SELECT * FROM orderdetails',
        'offices': 'SELECT * FROM offices'
    }

    # S3 client
    s3 = boto3.client('s3')
    bucket = 'classicmodels-data-lake'

    # Extract each table to CSV in S3
    for table_name, query in tables.items():
        print(f"Extracting {table_name}...")

        df = pd.read_sql(query, connection)
        csv_buffer = StringIO()
        df.to_csv(csv_buffer, index=False)

        s3.put_object(
            Bucket=bucket,
            Key=f'raw/{table_name}.csv',
            Body=csv_buffer.getvalue()
        )

        print(f"✅ {table_name}: {len(df)} records saved to S3")

    connection.close()
    print("✅ All tables extracted to S3")

if __name__ == "__main__":
    extract_to_s3()