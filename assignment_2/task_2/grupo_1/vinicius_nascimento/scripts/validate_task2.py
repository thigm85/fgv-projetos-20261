import argparse
import os
import sys
import boto3
import pymysql


def connect(args):
    return pymysql.connect(
        host=args.db_host,
        port=args.db_port,
        user=args.db_user,
        password=args.db_password,
        database=args.db_name,
        cursorclass=pymysql.cursors.DictCursor,
    )


def main():
    parser = argparse.ArgumentParser(description="Validação mínima da Task 2 incremental")
    parser.add_argument("--db-host", default=os.getenv("DB_HOST"), required=not os.getenv("DB_HOST"))
    parser.add_argument("--db-port", type=int, default=int(os.getenv("DB_PORT", "3306")))
    parser.add_argument("--db-user", default=os.getenv("DB_USER"), required=not os.getenv("DB_USER"))
    parser.add_argument("--db-password", default=os.getenv("DB_PASSWORD"), required=not os.getenv("DB_PASSWORD"))
    parser.add_argument("--db-name", default=os.getenv("DB_NAME", "classicmodels"))
    parser.add_argument("--bucket", default=os.getenv("ANALYTICS_BUCKET"), required=not os.getenv("ANALYTICS_BUCKET"))
    parser.add_argument("--prefix", default=os.getenv("FACT_PREFIX", "analytics/fact_orders/"))
    parser.add_argument("--pipeline-name", default="classicmodels_sales")
    args = parser.parse_args()

    errors = []

    with connect(args) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT pipeline_name, last_processed_order_date, last_run_at, last_run_status
                FROM etl_watermark
                WHERE pipeline_name = %s
                """,
                (args.pipeline_name,),
            )
            wm = cur.fetchone()

            if not wm:
                errors.append("Watermark classicmodels_sales não encontrado.")
            else:
                if wm["last_processed_order_date"] is None:
                    errors.append("last_processed_order_date está NULL.")
                if wm["last_run_status"] != "SUCCEEDED":
                    errors.append(f"last_run_status esperado SUCCEEDED, recebido {wm['last_run_status']}.")

            cur.execute("SELECT MAX(orderDate) AS max_order_date FROM orders")
            max_order_date = cur.fetchone()["max_order_date"]

            if wm and wm["last_processed_order_date"] != max_order_date:
                errors.append(
                    f"Watermark ({wm['last_processed_order_date']}) diferente de MAX(orderDate) ({max_order_date})."
                )

    s3 = boto3.client("s3")
    paginator = s3.get_paginator("list_objects_v2")
    found_partitioned_objects = False
    for page in paginator.paginate(Bucket=args.bucket, Prefix=args.prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if "order_year=" in key and "order_month=" in key and key.endswith(".parquet"):
                found_partitioned_objects = True
                break
        if found_partitioned_objects:
            break

    if not found_partitioned_objects:
        errors.append("Não encontrei Parquet particionado em fact_orders/order_year=*/order_month=*/.")

    if errors:
        print("VALIDAÇÃO FALHOU")
        for error in errors:
            print(f"- {error}")
        return 1

    print("VALIDAÇÃO OK")
    print("- Watermark avançado até MAX(orderDate)")
    print("- Objetos Parquet particionados encontrados no S3")
    return 0


if __name__ == "__main__":
    sys.exit(main())
