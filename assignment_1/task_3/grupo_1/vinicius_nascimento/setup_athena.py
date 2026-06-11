import boto3
import time
import sys
from pathlib import Path

REGION = "us-east-1"
DATABASE = "classicmodels_analytics"
RESULTS_PREFIX = "athena-results/"

BASE_DIR = Path(__file__).resolve().parent
BUCKET_FILE = BASE_DIR / "bucket_name.txt"


def read_bucket_name() -> str:
    if not BUCKET_FILE.exists():
        print("ERRO: bucket_name.txt não encontrado na pasta da Task 3.")
        print("Copie o bucket_name.txt gerado na Task 2 para esta pasta.")
        sys.exit(1)
    bucket = BUCKET_FILE.read_text(encoding="utf-8").strip()
    if not bucket:
        print("ERRO: bucket_name.txt está vazio.")
        sys.exit(1)
    return bucket


def run_query(athena, query: str, database: str | None, output_location: str) -> None:
    params = {
        "QueryString": query,
        "ResultConfiguration": {"OutputLocation": output_location},
    }
    if database:
        params["QueryExecutionContext"] = {"Database": database}

    response = athena.start_query_execution(**params)
    qid = response["QueryExecutionId"]

    while True:
        result = athena.get_query_execution(QueryExecutionId=qid)
        state = result["QueryExecution"]["Status"]["State"]

        if state == "SUCCEEDED":
            print(f"[OK] Query executada: {qid}")
            return
        if state in ["FAILED", "CANCELLED"]:
            reason = result["QueryExecution"]["Status"].get("StateChangeReason", "sem detalhes")
            print("QUERY QUE FALHOU:\n", query)
            print(f"ERRO Athena: {state} - {reason}")
            sys.exit(1)

        time.sleep(2)


def main():
    bucket = read_bucket_name()
    output_location = f"s3://{bucket}/{RESULTS_PREFIX}"
    athena = boto3.client("athena", region_name=REGION)

    print(f"Usando bucket: {bucket}")
    print(f"Database Athena: {DATABASE}")
    print(f"Resultados Athena: {output_location}")

    run_query(
        athena,
        f"CREATE DATABASE IF NOT EXISTS {DATABASE}",
        None,
        output_location,
    )

    drop_queries = [
        f"DROP TABLE IF EXISTS {DATABASE}.fact_orders",
        f"DROP TABLE IF EXISTS {DATABASE}.dim_customers",
        f"DROP TABLE IF EXISTS {DATABASE}.dim_products",
        f"DROP TABLE IF EXISTS {DATABASE}.dim_dates",
        f"DROP TABLE IF EXISTS {DATABASE}.dim_countries",
    ]

    for drop in drop_queries:
        run_query(athena, drop, DATABASE, output_location)
        
    ddl_queries = [
        f"""
        CREATE EXTERNAL TABLE IF NOT EXISTS {DATABASE}.fact_orders (
            order_id int,
            customer_id int,
            product_id string,
            order_date_key int,
            country_key bigint,
            quantity_ordered int,
            price_each decimal(10,2),
            sales_amount decimal(20,2)
        )
        STORED AS PARQUET
        LOCATION 's3://{bucket}/fact_orders/'
        """,
        f"""
        CREATE EXTERNAL TABLE IF NOT EXISTS {DATABASE}.dim_customers (
            customer_id int,
            customer_name string,
            contact_name string,
            city string,
            country string
        )
        STORED AS PARQUET
        LOCATION 's3://{bucket}/dim_customers/'
        """,
        f"""
        CREATE EXTERNAL TABLE IF NOT EXISTS {DATABASE}.dim_products (
            product_id string,
            product_name string,
            product_line string,
            product_vendor string
        )
        STORED AS PARQUET
        LOCATION 's3://{bucket}/dim_products/'
        """,
        f"""
        CREATE EXTERNAL TABLE IF NOT EXISTS {DATABASE}.dim_dates (
            date_key int,
            full_date date,
            year int,
            quarter int,
            month int,
            day int
        )
        STORED AS PARQUET
        LOCATION 's3://{bucket}/dim_dates/'
        """,
        f"""
        CREATE EXTERNAL TABLE IF NOT EXISTS {DATABASE}.dim_countries (
            country string,
            country_key bigint,
            territory string
        )
        STORED AS PARQUET
        LOCATION 's3://{bucket}/dim_countries/'
        """,
    ]

    for ddl in ddl_queries:
        run_query(athena, ddl, DATABASE, output_location)

    print("\nSUCESSO: tabelas externas criadas no Athena.")
    print("Agora rode: python validate_athena.py")


if __name__ == "__main__":
    main()
