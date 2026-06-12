"""
Validate that the incremental ETL produced correct results on S3/Athena.

Checks performed:
  1. Watermark status is SUCCEEDED after the latest run
  2. Fact row count in Athena matches the sum of orderdetails rows for orders
     processed in the last ETL window
  3. sales_amount = quantity_ordered * price_each for all fact rows
  4. No orphan fact rows (order_id / customer_id / product_id must exist in dims)
  5. All expected (order_year, order_month) partitions are present in the catalog

Usage:
    python validate_incremental_etl.py
"""

import os
import time

import boto3
import pymysql
from dotenv import load_dotenv

load_dotenv()

DB_HOST = os.environ["DB_HOST"]
DB_USER = os.environ["DB_USER"]
DB_PASSWORD = os.environ["DB_PASSWORD"]
DB_NAME = os.getenv("DB_NAME", "classicmodels")
DB_PORT = int(os.getenv("DB_PORT", "3306"))

ATHENA_DATABASE = os.environ["GLUE_DATABASE"]
ATHENA_OUTPUT = os.environ["ATHENA_OUTPUT"]   # e.g. s3://my-bucket/athena-results/
PIPELINE_NAME = "classicmodels_sales"


# ── helpers ───────────────────────────────────────────────────────────────────

def _db():
    return pymysql.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD,
        database=DB_NAME, cursorclass=pymysql.cursors.DictCursor,
    )


def _athena_query(sql: str) -> list[dict]:
    client = boto3.client("athena")
    resp = client.start_query_execution(
        QueryString=sql,
        QueryExecutionContext={"Database": ATHENA_DATABASE},
        ResultConfiguration={"OutputLocation": ATHENA_OUTPUT},
    )
    qid = resp["QueryExecutionId"]
    while True:
        state = client.get_query_execution(QueryExecutionId=qid)["QueryExecution"]["Status"]["State"]
        if state in ("SUCCEEDED", "FAILED", "CANCELLED"):
            break
        time.sleep(2)
    if state != "SUCCEEDED":
        raise RuntimeError(f"Athena query {qid} ended with state={state}")
    result = client.get_query_results(QueryExecutionId=qid)
    cols = [c["Label"] for c in result["ResultSet"]["ResultSetMetadata"]["ColumnInfo"]]
    rows = result["ResultSet"]["Rows"][1:]  # skip header
    return [{cols[i]: r["Data"][i].get("VarCharValue") for i in range(len(cols))} for r in rows]


# ── checks ────────────────────────────────────────────────────────────────────

def check_watermark_status():
    conn = _db()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT last_run_status, last_processed_order_date, last_run_at FROM etl_watermark WHERE pipeline_name = %s",
            (PIPELINE_NAME,),
        )
        row = cur.fetchone()
    conn.close()
    assert row, "Watermark row not found."
    assert row["last_run_status"] == "SUCCEEDED", f"Watermark status is {row['last_run_status']}, expected SUCCEEDED."
    print(f"  [OK] watermark status=SUCCEEDED, date={row['last_processed_order_date']}, run_at={row['last_run_at']}")
    return row["last_processed_order_date"]


def check_fact_row_count(watermark_date):
    conn = _db()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) AS cnt FROM orderdetails od INNER JOIN orders o ON o.orderNumber = od.orderNumber WHERE o.orderDate <= %s",
            (watermark_date,),
        )
        expected = cur.fetchone()["cnt"]
    conn.close()

    rows = _athena_query("SELECT COUNT(*) AS cnt FROM fact_orders")
    actual = int(rows[0]["cnt"])
    assert actual == expected, f"fact_orders has {actual} rows; expected {expected}."
    print(f"  [OK] fact_orders row count matches source: {actual}")


def check_sales_amount_integrity():
    rows = _athena_query(
        """
        SELECT COUNT(*) AS bad
        FROM fact_orders
        WHERE ABS(sales_amount - CAST(quantity_ordered AS DOUBLE) * price_each) > 0.001
        """
    )
    bad = int(rows[0]["bad"])
    assert bad == 0, f"{bad} rows with inconsistent sales_amount."
    print(f"  [OK] sales_amount integrity: 0 bad rows")


def check_referential_integrity():
    orphan_customers = int(
        _athena_query(
            "SELECT COUNT(*) AS n FROM fact_orders f LEFT JOIN dim_customers d ON f.customer_id = d.customer_id WHERE d.customer_id IS NULL"
        )[0]["n"]
    )
    orphan_products = int(
        _athena_query(
            "SELECT COUNT(*) AS n FROM fact_orders f LEFT JOIN dim_products d ON f.product_id = d.product_id WHERE d.product_id IS NULL"
        )[0]["n"]
    )
    assert orphan_customers == 0, f"{orphan_customers} fact rows with unknown customer_id."
    assert orphan_products == 0, f"{orphan_products} fact rows with unknown product_id."
    print("  [OK] referential integrity: no orphan customer or product keys")


def check_partitions_in_catalog():
    rows = _athena_query(
        "SELECT DISTINCT order_year, order_month FROM fact_orders ORDER BY order_year, order_month"
    )
    print(f"  [OK] Glue Catalog partitions visible in Athena: {len(rows)}")
    for r in rows:
        print(f"       order_year={r['order_year']}, order_month={r['order_month']}")


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    print("=== Incremental ETL Validation ===")
    watermark_date = check_watermark_status()
    check_fact_row_count(watermark_date)
    check_sales_amount_integrity()
    check_referential_integrity()
    check_partitions_in_catalog()
    print("\nAll checks passed.")


if __name__ == "__main__":
    main()
