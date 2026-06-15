"""JDBC extraction: watermark read and incremental delta from classicmodels."""

from __future__ import annotations

from dataclasses import dataclass

from pipeline.spark_helpers import is_empty
from pyspark.sql import DataFrame, SparkSession

_MYSQL_DRIVER = "com.mysql.cj.jdbc.Driver"


def _read_query(*, spark: SparkSession, url: str, user: str, password: str, query: str) -> DataFrame:
    wrapped = f"({query}) AS incremental_src"
    return (
        spark.read.format("jdbc")
        .option("url", url)
        .option("dbtable", wrapped)
        .option("user", user)
        .option("password", password)
        .option("driver", _MYSQL_DRIVER)
        .load()
    )


def _sql_in_ints(values: list[int]) -> str:
    return ",".join(str(v) for v in values)


def _sql_in_strings(values: list[str]) -> str:
    escaped = (v.replace("'", "''") for v in values)
    return ",".join(f"'{v}'" for v in escaped)


def read_watermark(
    *,
    spark: SparkSession,
    jdbc_url: str,
    user: str,
    password: str,
    pipeline_name: str,
    watermark_table: str,
) -> dict:
    sql = (
        f"SELECT pipeline_name, last_processed_order_date, last_run_at, last_run_status "
        f"FROM {watermark_table} WHERE pipeline_name = '{pipeline_name}'"
    )
    rows = _read_query(spark=spark, url=jdbc_url, user=user, password=password, query=sql).collect()
    if not rows:
        raise ValueError(f"Watermark row missing for pipeline_name={pipeline_name}")
    row = rows[0]
    return {
        "pipeline_name": row["pipeline_name"],
        "last_processed_order_date": row["last_processed_order_date"],
        "last_run_at": row["last_run_at"],
        "last_run_status": row["last_run_status"],
    }


@dataclass
class DeltaExtract:
    orders: DataFrame
    orderdetails: DataFrame
    customers: DataFrame
    products: DataFrame
    productlines: DataFrame
    employees: DataFrame
    offices: DataFrame


def extract_delta(
    *,
    spark: SparkSession,
    jdbc_url: str,
    user: str,
    password: str,
    cutoff: str,
) -> DeltaExtract | None:
    """Extract order delta and dimension sources. Returns None when there are no new orders."""
    orders = _read_query(
        spark=spark,
        url=jdbc_url,
        user=user,
        password=password,
        query=f"SELECT * FROM orders WHERE orderDate > DATE('{cutoff}')",
    )
    if is_empty(orders):
        return None

    order_numbers = [int(r["orderNumber"]) for r in orders.select("orderNumber").distinct().collect()]
    order_in = _sql_in_ints(order_numbers)

    orderdetails = _read_query(
        spark=spark,
        url=jdbc_url,
        user=user,
        password=password,
        query=f"SELECT * FROM orderdetails WHERE orderNumber IN ({order_in})",
    )

    customer_numbers = [
        int(r["customerNumber"]) for r in orders.select("customerNumber").distinct().collect()
    ]
    customer_in = _sql_in_ints(customer_numbers)

    product_codes = [
        str(r["productCode"]) for r in orderdetails.select("productCode").distinct().collect()
    ]
    product_in = _sql_in_strings(product_codes)

    customers = _read_query(
        spark=spark,
        url=jdbc_url,
        user=user,
        password=password,
        query=f"SELECT * FROM customers WHERE customerNumber IN ({customer_in})",
    )
    products = _read_query(
        spark=spark,
        url=jdbc_url,
        user=user,
        password=password,
        query=f"SELECT * FROM products WHERE productCode IN ({product_in})",
    )
    productlines = _read_query(
        spark=spark,
        url=jdbc_url,
        user=user,
        password=password,
        query=(
            "SELECT * FROM productlines WHERE productLine IN ("
            f"SELECT DISTINCT productLine FROM products WHERE productCode IN ({product_in})"
            ")"
        ),
    )
    employees = _read_query(
        spark=spark,
        url=jdbc_url,
        user=user,
        password=password,
        query=(
            "SELECT * FROM employees WHERE employeeNumber IN ("
            "SELECT DISTINCT salesRepEmployeeNumber FROM customers "
            f"WHERE customerNumber IN ({customer_in}) AND salesRepEmployeeNumber IS NOT NULL"
            ")"
        ),
    )
    offices = _read_query(
        spark=spark,
        url=jdbc_url,
        user=user,
        password=password,
        query=(
            "SELECT * FROM offices WHERE officeCode IN ("
            "SELECT DISTINCT officeCode FROM employees WHERE employeeNumber IN ("
            "SELECT DISTINCT salesRepEmployeeNumber FROM customers "
            f"WHERE customerNumber IN ({customer_in}) AND salesRepEmployeeNumber IS NOT NULL"
            "))"
        ),
    )

    return DeltaExtract(
        orders=orders,
        orderdetails=orderdetails,
        customers=customers,
        products=products,
        productlines=productlines,
        employees=employees,
        offices=offices,
    )
