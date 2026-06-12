#!/usr/bin/env python3
"""
Assignment 2 — Task 2: Incremental Glue ETL Job
=================================================
Este script roda no AWS Glue (PySpark) e implementa ETL incremental:
  1. Lê o watermark (etl_watermark) para obter last_processed_order_date
  2. Extrai apenas pedidos novos (orderDate > watermark) via JDBC
  3. Reprocessa dimensões completas (Opção A)
  4. Grava fact_orders particionado por order_year/order_month
  5. Atualiza o watermark somente em caso de sucesso
"""

import sys
import logging
import traceback
from datetime import datetime

from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from awsglue.context import GlueContext
from awsglue.job import Job
from pyspark.sql import functions as F
from pyspark.sql.window import Window
import boto3
import json

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# ---------------------------------------------------------------------------
# Job arguments
# ---------------------------------------------------------------------------
args = getResolvedOptions(
    sys.argv,
    [
        "JOB_NAME",
        "CONNECTION_NAME",
        "JDBC_URL",
        "DATABASE_NAME",
        "S3_OUTPUT_PATH",
        "AWS_REGION",
        "RDS_SECRET_ARN",
    ],
)

sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)
job.init(args["JOB_NAME"], args)

# Enable dynamic partition overwrite so only touched partitions are replaced
spark.conf.set("spark.sql.sources.partitionOverwriteMode", "dynamic")

# ---------------------------------------------------------------------------
# Credentials helper
# ---------------------------------------------------------------------------

def get_db_credentials(secret_arn: str, region: str) -> dict:
    """Retrieve RDS credentials from AWS Secrets Manager."""
    if not secret_arn:
        return {}
    client = boto3.client("secretsmanager", region_name=region)
    resp = client.get_secret_value(SecretId=secret_arn)
    return json.loads(resp.get("SecretString", "{}"))


creds = get_db_credentials(args.get("RDS_SECRET_ARN"), args.get("AWS_REGION"))
db_user = creds.get("username") or "admin"
db_password = creds.get("password") or ""
output_path = args["S3_OUTPUT_PATH"].rstrip("/") + "/"
jdbc_url = args["JDBC_URL"]

PIPELINE_NAME = "classicmodels_sales"
WATERMARK_TABLE = "etl_watermark"

# ---------------------------------------------------------------------------
# JDBC read helper
# ---------------------------------------------------------------------------

def read_jdbc_table(table_name: str, predicate: str = None):
    """Read a table from RDS via JDBC, optionally with a WHERE predicate."""
    reader = (
        spark.read.format("jdbc")
        .option("url", jdbc_url)
        .option("user", db_user)
        .option("password", db_password)
        .option("driver", "com.mysql.cj.jdbc.Driver")
    )
    if predicate:
        reader = reader.option("dbtable", f"(SELECT * FROM {table_name} WHERE {predicate}) AS t")
    else:
        reader = reader.option("dbtable", table_name)
    return reader.load()


def write_jdbc(sql_statement: str):
    """Execute a write SQL statement on RDS via a JDBC connection (PyMySQL via boto3 not available in Glue by default,
    so we use Spark JDBC with a dummy read followed by raw JDBC through the driver)."""
    # Use py4j to get a raw JDBC connection from the Spark driver
    driver_class = "com.mysql.cj.jdbc.Driver"
    sc._jvm.java.lang.Class.forName(driver_class)
    conn = sc._jvm.java.sql.DriverManager.getConnection(jdbc_url, db_user, db_password)
    try:
        stmt = conn.createStatement()
        stmt.executeUpdate(sql_statement)
        conn.commit()
    finally:
        conn.close()


# ===========================================================================
#  MAIN ETL
# ===========================================================================
etl_succeeded = False
max_order_date_str = None

try:
    logger.info("=" * 60)
    logger.info(f"Starting INCREMENTAL ETL: {args['JOB_NAME']}")
    logger.info("=" * 60)

    # ------------------------------------------------------------------
    # 3.2.1 — Read watermark
    # ------------------------------------------------------------------
    logger.info("[STEP 1] Reading watermark...")

    watermark_df = read_jdbc_table(
        WATERMARK_TABLE,
        f"pipeline_name = '{PIPELINE_NAME}'"
    )

    if watermark_df.count() == 0:
        logger.warning("No watermark found — treating as first incremental run (NEVER_RUN).")
        last_processed_date = "1900-01-01"
        watermark_status = "NEVER_RUN"
    else:
        wm_row = watermark_df.collect()[0]
        raw_date = wm_row["last_processed_order_date"]
        watermark_status = str(wm_row["last_run_status"])

        if raw_date is None or watermark_status == "NEVER_RUN":
            last_processed_date = "1900-01-01"
            logger.info("Watermark status is NEVER_RUN — will process all historical data.")
        else:
            last_processed_date = str(raw_date)

    logger.info(f"  Watermark date  : {last_processed_date}")
    logger.info(f"  Watermark status: {watermark_status}")

    # ------------------------------------------------------------------
    # 3.2.2 — Incremental extraction via JDBC
    # ------------------------------------------------------------------
    logger.info("[STEP 2] Extracting delta from JDBC...")

    # Incremental orders
    orders_df = read_jdbc_table("orders", f"orderDate > '{last_processed_date}'")
    delta_count = orders_df.count()
    logger.info(f"  Delta orders extracted: {delta_count}")

    if delta_count == 0:
        logger.info("No new orders to process. Updating watermark status and exiting.")
        # Even with no data, mark as succeeded
        now_utc = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        write_jdbc(
            f"UPDATE {WATERMARK_TABLE} SET "
            f"last_run_at = '{now_utc}', "
            f"last_run_status = 'SUCCEEDED' "
            f"WHERE pipeline_name = '{PIPELINE_NAME}'"
        )
        job.commit()
        sys.exit(0)

    # Get delta order numbers for filtering orderdetails
    delta_order_numbers = [row["orderNumber"] for row in orders_df.select("orderNumber").collect()]
    order_list_str = ",".join(str(o) for o in delta_order_numbers)

    # Incremental orderdetails
    orderdetails_df = read_jdbc_table("orderdetails", f"orderNumber IN ({order_list_str})")
    logger.info(f"  Delta orderdetails extracted: {orderdetails_df.count()}")

    # Full dimension tables (Opção A — reprocess completo)
    logger.info("  Extracting full dimension tables...")
    customers_df = read_jdbc_table("customers")
    products_df = read_jdbc_table("products")
    productlines_df = read_jdbc_table("productlines")
    logger.info(f"  customers={customers_df.count()}, products={products_df.count()}, productlines={productlines_df.count()}")

    # ------------------------------------------------------------------
    # 3.2.3 — Transformation to star schema
    # ------------------------------------------------------------------
    logger.info("[STEP 3] Transforming to star schema...")

    # -- dim_dates (from delta orders only — union with existing later or full rebuild)
    # We rebuild dim_dates from ALL orders to keep it complete
    all_orders_df = read_jdbc_table("orders")
    dim_dates = all_orders_df.select(
        F.col("orderDate").cast("date").alias("full_date"),
        F.date_format(F.col("orderDate"), "yyyyMMdd").cast("int").alias("date_key"),
        F.year(F.col("orderDate")).alias("year"),
        F.quarter(F.col("orderDate")).alias("quarter"),
        F.month(F.col("orderDate")).alias("month"),
        F.dayofmonth(F.col("orderDate")).alias("day"),
    ).dropna().distinct()

    # -- dim_customers
    dim_customers = customers_df.select(
        F.col("customerNumber").alias("customer_id"),
        F.col("customerName").alias("customer_name"),
        F.concat(F.col("contactFirstName"), F.lit(" "), F.col("contactLastName")).alias("contact_name"),
        F.col("city"),
        F.col("country"),
    ).distinct()

    # -- dim_products
    products_full = products_df.join(productlines_df, "productLine", "left")
    dim_products = products_full.select(
        F.col("productCode").alias("product_id"),
        F.col("productName").alias("product_name"),
        F.col("productLine").alias("product_line"),
        F.col("productVendor").alias("product_vendor"),
    ).distinct()

    # -- dim_countries
    dim_countries = (
        customers_df.select(F.col("country"))
        .distinct()
        .withColumn("country_key", F.row_number().over(Window.orderBy(F.col("country"))))
        .withColumn("territory", F.lit(None).cast("string"))
    )

    # -- fact_orders (DELTA only)
    orders_with_details = (
        orders_df.join(orderdetails_df, "orderNumber", "inner")
        .join(customers_df, "customerNumber", "inner")
        .join(products_df, "productCode", "inner")
    )

    orders_with_country = orders_with_details.join(
        dim_countries.select("country", "country_key"),
        "country",
        "left",
    )

    fact_orders_delta = (
        orders_with_country.withColumn(
            "order_date_key",
            F.date_format(F.col("orderDate"), "yyyyMMdd").cast("int"),
        )
        .select(
            F.col("orderNumber").alias("order_id"),
            F.col("customerNumber").alias("customer_id"),
            F.col("productCode").alias("product_id"),
            F.col("order_date_key"),
            F.coalesce(F.col("country_key"), F.lit(0)).alias("country_key"),
            F.col("quantityOrdered").alias("quantity_ordered"),
            F.col("priceEach").cast("decimal(10,2)").alias("price_each"),
            (F.col("quantityOrdered") * F.col("priceEach")).cast("decimal(12,2)").alias("sales_amount"),
            F.year(F.col("orderDate")).alias("order_year"),
            F.month(F.col("orderDate")).alias("order_month"),
        )
        .distinct()
    )

    # -- Validate sales_amount consistency
    validation_count = fact_orders_delta.where(
        F.col("sales_amount") != (F.col("quantity_ordered") * F.col("price_each"))
    ).count()
    if validation_count == 0:
        logger.info("  ✓ sales_amount validation passed for delta")
    else:
        logger.warning(f"  ⚠ {validation_count} rows with inconsistent sales_amount in delta")

    # ------------------------------------------------------------------
    # 3.2.4 — Load / merge into fact
    # ------------------------------------------------------------------
    logger.info("[STEP 4] Loading data to S3...")

    # Determine affected partitions
    affected_partitions = (
        fact_orders_delta.select("order_year", "order_month")
        .distinct()
        .collect()
    )
    logger.info(f"  Affected partitions: {[(r['order_year'], r['order_month']) for r in affected_partitions]}")

    # Read existing data from affected partitions and merge
    fact_orders_path = f"{output_path}fact_orders/"

    # Try to read existing fact_orders for the affected partitions
    try:
        existing_fact = spark.read.parquet(fact_orders_path)
        # Filter only affected partitions
        partition_filter = None
        for p in affected_partitions:
            cond = (F.col("order_year") == p["order_year"]) & (F.col("order_month") == p["order_month"])
            partition_filter = cond if partition_filter is None else (partition_filter | cond)

        existing_affected = existing_fact.where(partition_filter)
        # Remove duplicates: keep delta rows for matching keys
        existing_deduped = existing_affected.join(
            fact_orders_delta.select("order_id", "product_id"),
            on=["order_id", "product_id"],
            how="left_anti",
        )
        # Union existing (deduped) + delta
        merged_fact = existing_deduped.unionByName(fact_orders_delta)
        logger.info(f"  Merged: {existing_deduped.count()} existing + {fact_orders_delta.count()} delta")
    except Exception:
        # No existing data — first run
        merged_fact = fact_orders_delta
        logger.info(f"  First run: writing {fact_orders_delta.count()} rows")

    # Write with dynamic partition overwrite
    merged_fact.write.partitionBy("order_year", "order_month").mode("overwrite").option(
        "compression", "snappy"
    ).parquet(fact_orders_path)

    logger.info(f"  ✓ fact_orders written to {fact_orders_path}")

    # Write dimensions (full overwrite)
    write_opts = {"mode": "overwrite", "compression": "snappy"}
    dim_customers.coalesce(1).write.parquet(f"{output_path}dim_customers/", **write_opts)
    dim_products.coalesce(1).write.parquet(f"{output_path}dim_products/", **write_opts)
    dim_dates.coalesce(1).write.parquet(f"{output_path}dim_dates/", **write_opts)
    dim_countries.coalesce(1).write.parquet(f"{output_path}dim_countries/", **write_opts)

    logger.info(
        f"  ✓ Dimensions written: dim_customers={dim_customers.count()}, "
        f"dim_products={dim_products.count()}, dim_dates={dim_dates.count()}, "
        f"dim_countries={dim_countries.count()}"
    )

    # Compute max order date for watermark update
    max_order_date_row = fact_orders_delta.agg(
        F.max(
            F.to_date(F.col("order_date_key").cast("string"), "yyyyMMdd")
        ).alias("max_date")
    ).collect()[0]
    max_order_date_str = str(max_order_date_row["max_date"])

    etl_succeeded = True
    logger.info(f"  Max order date in delta: {max_order_date_str}")

    # ------------------------------------------------------------------
    # 3.2.5 — Update watermark
    # ------------------------------------------------------------------
    logger.info("[STEP 5] Updating watermark...")
    now_utc = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    write_jdbc(
        f"UPDATE {WATERMARK_TABLE} SET "
        f"last_processed_order_date = '{max_order_date_str}', "
        f"last_run_at = '{now_utc}', "
        f"last_run_status = 'SUCCEEDED' "
        f"WHERE pipeline_name = '{PIPELINE_NAME}'"
    )
    logger.info("  ✓ Watermark updated: SUCCEEDED")

    logger.info("=" * 60)
    logger.info(f"✓ INCREMENTAL ETL COMPLETED SUCCESSFULLY")
    logger.info(f"  Delta rows   : {delta_count}")
    logger.info(f"  Max orderDate: {max_order_date_str}")
    logger.info("=" * 60)

    job.commit()

except Exception as e:
    logger.error(f"✗ ETL FAILED: {str(e)}")
    logger.error(traceback.format_exc())

    # Update watermark to FAILED without advancing the date
    try:
        now_utc = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        write_jdbc(
            f"UPDATE {WATERMARK_TABLE} SET "
            f"last_run_at = '{now_utc}', "
            f"last_run_status = 'FAILED' "
            f"WHERE pipeline_name = '{PIPELINE_NAME}'"
        )
        logger.info("  Watermark updated: FAILED (date NOT advanced)")
    except Exception as wm_err:
        logger.error(f"  Could not update watermark on failure: {wm_err}")

    job.commit()
    sys.exit(1)
