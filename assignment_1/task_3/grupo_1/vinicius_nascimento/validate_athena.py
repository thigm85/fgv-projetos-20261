import boto3
import time
import sys
from pathlib import Path

REGION = "us-east-1"
DATABASE = "classicmodels_analytics"
RESULTS_PREFIX = "athena-results/"
BASE_DIR = Path(__file__).resolve().parent
BUCKET_FILE = BASE_DIR / "bucket_name.txt"


def read_bucket_name():
    if not BUCKET_FILE.exists():
        print("ERRO: bucket_name.txt não encontrado. Copie o arquivo da Task 2 para esta pasta.")
        sys.exit(1)
    return BUCKET_FILE.read_text(encoding="utf-8").strip()


def run_query(athena, query, output_location):
    response = athena.start_query_execution(
        QueryString=query,
        QueryExecutionContext={"Database": DATABASE},
        ResultConfiguration={"OutputLocation": output_location},
    )
    qid = response["QueryExecutionId"]

    while True:
        status = athena.get_query_execution(QueryExecutionId=qid)["QueryExecution"]["Status"]
        state = status["State"]
        if state == "SUCCEEDED":
            break
        if state in ["FAILED", "CANCELLED"]:
            print("QUERY QUE FALHOU:\n", query)
            print(status.get("StateChangeReason", "sem detalhes"))
            sys.exit(1)
        time.sleep(2)

    rows = athena.get_query_results(QueryExecutionId=qid)["ResultSet"]["Rows"]
    if len(rows) < 2:
        return None
    return rows[1]["Data"][0].get("VarCharValue")


def assert_true(name, condition, value=None):
    if condition:
        print(f"[PASS] {name}" + (f" | valor={value}" if value is not None else ""))
        return 0
    print(f"[FAIL] {name}" + (f" | valor={value}" if value is not None else ""))
    return 1


def main():
    bucket = read_bucket_name()
    output_location = f"s3://{bucket}/{RESULTS_PREFIX}"
    athena = boto3.client("athena", region_name=REGION)
    failures = 0

    tables = ["fact_orders", "dim_customers", "dim_products", "dim_dates", "dim_countries"]

    for table in tables:
        count = run_query(athena, f"SELECT COUNT(*) FROM {table}", output_location)
        failures += assert_true(f"{table} possui registros", int(count) > 0, count)

    invalid_customers = run_query(
        athena,
        """
        SELECT COUNT(*)
        FROM fact_orders f
        LEFT JOIN dim_customers c ON f.customer_id = c.customer_id
        WHERE c.customer_id IS NULL
        """,
        output_location,
    )
    failures += assert_true("fact_orders referencia customer_id válido", int(invalid_customers) == 0, invalid_customers)

    invalid_products = run_query(
        athena,
        """
        SELECT COUNT(*)
        FROM fact_orders f
        LEFT JOIN dim_products p ON f.product_id = p.product_id
        WHERE p.product_id IS NULL
        """,
        output_location,
    )
    failures += assert_true("fact_orders referencia product_id válido", int(invalid_products) == 0, invalid_products)

    invalid_sales = run_query(
        athena,
        """
        SELECT COUNT(*)
        FROM fact_orders
        WHERE ABS(sales_amount - quantity_ordered * price_each) > 0.01
        """,
        output_location,
    )
    failures += assert_true("sales_amount = quantity_ordered * price_each", int(invalid_sales) == 0, invalid_sales)

    if failures == 0:
        print("\nRESULTADO: Task 3 validada com sucesso no Athena.")
        sys.exit(0)

    print(f"\nRESULTADO: Task 3 com {failures} falha(s).")
    sys.exit(1)


if __name__ == "__main__":
    main()
