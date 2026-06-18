import sys
import logging
import datetime

class NormalExit(Exception):
    """Custom exception to signal a clean, successful exit without raising errors in Glue."""
    pass

from awsglue.transforms import *
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from awsglue.context import GlueContext
from awsglue.job import Job
from pyspark.sql import functions as F
from pyspark.sql.types import IntegerType

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("etl_job_incremental")

args = getResolvedOptions(sys.argv, [
    "JOB_NAME",
    "S3_OUTPUT_PATH",
    "JDBC_CONNECTION_URL",
    "DB_USER",
    "DB_PASSWORD",
    "DB_NAME",
    "CONNECTION_NAME"
])

sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)
job.init(args["JOB_NAME"], args)

# Enable dynamic partition overwrite so only touched partitions are replaced
spark.conf.set("spark.sql.sources.partitionOverwriteMode", "dynamic")

s3_output = args["S3_OUTPUT_PATH"]
jdbc_url = args["JDBC_CONNECTION_URL"]
db_user = args["DB_USER"]
db_password = args["DB_PASSWORD"]
db_name = args["DB_NAME"]

PIPELINE_NAME = "classicmodels_sales"
WATERMARK_TABLE = "etl_watermark"

connection_options = {
    "url": jdbc_url,
    "user": db_user,
    "password": db_password,
}


def read_table(table_name, predicate=None):
    """Read a table from RDS via JDBC, optionally with a pushdown predicate."""
    logger.info(f"Extracting table: {db_name}.{table_name}")
    opts = {**connection_options, "dbtable": f"{db_name}.{table_name}"}
    if predicate:
        opts["dbtable"] = f"(SELECT * FROM {db_name}.{table_name} WHERE {predicate}) AS t"
        logger.info(f"  -> pushdown predicate: {predicate}")
    df = spark.read.format("jdbc").options(**opts).load()
    row_count = df.count()
    logger.info(f"  -> {table_name}: {row_count} rows extracted")
    if row_count == 0:
        logger.warning(f"  -> WARNING: {table_name} returned 0 rows")
    return df


def read_watermark():
    """Read the current watermark from the etl_watermark table."""
    logger.info("Reading watermark from etl_watermark...")
    wm_df = spark.read.format("jdbc").options(
        **connection_options,
        dbtable=(
            f"(SELECT last_processed_order_date, last_run_status"
            f" FROM {db_name}.{WATERMARK_TABLE}"
            f" WHERE pipeline_name = '{PIPELINE_NAME}') AS wm"
        )
    ).load()

    if wm_df.count() == 0:
        logger.warning("No watermark row found — will run full load.")
        return None, "NEVER_RUN"

    row = wm_df.collect()[0]
    last_date = row["last_processed_order_date"]
    last_status = row["last_run_status"]
    logger.info(f"  -> last_processed_order_date = {last_date}")
    logger.info(f"  -> last_run_status = {last_status}")
    return last_date, last_status


def update_watermark(new_date, status):
    """Update the watermark row in the RDS etl_watermark table via JDBC."""
    import pymysql

    # Use pymysql directly for the UPDATE since Spark JDBC is read-oriented.
    # In Glue, pymysql is available as an included dependency.
    logger.info(f"Updating watermark: date={new_date}, status={status}")

    # Parse JDBC URL to get host/port
    # jdbc:mysql://host:port/database
    jdbc_parts = jdbc_url.replace("jdbc:mysql://", "").split("/")
    host_port = jdbc_parts[0]
    if ":" in host_port:
        host, port = host_port.split(":")
        port = int(port)
    else:
        host = host_port
        port = 3306

    conn = pymysql.connect(
        host=host,
        port=port,
        user=db_user,
        password=db_password,
        database=db_name,
        autocommit=False,
    )
    try:
        with conn.cursor() as cursor:
            now_utc = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            if status == "SUCCEEDED":
                cursor.execute(
                    f"UPDATE {WATERMARK_TABLE}"
                    f" SET last_processed_order_date = %s,"
                    f"     last_run_at = %s,"
                    f"     last_run_status = %s"
                    f" WHERE pipeline_name = %s",
                    (str(new_date), now_utc, status, PIPELINE_NAME),
                )
            else:
                # FAILED — do NOT advance the date
                cursor.execute(
                    f"UPDATE {WATERMARK_TABLE}"
                    f" SET last_run_at = %s,"
                    f"     last_run_status = %s"
                    f" WHERE pipeline_name = %s",
                    (now_utc, status, PIPELINE_NAME),
                )
        conn.commit()
        logger.info("Watermark updated successfully.")
    finally:
        conn.close()


# ============================================================================
# MAIN ETL LOGIC
# ============================================================================

try:
    # --- STEP 0: READ WATERMARK ---

    logger.info("=" * 60)
    logger.info("STEP 0/4 - READ WATERMARK")
    logger.info("=" * 60)

    last_processed_date, last_status = read_watermark()

    is_full_load = (last_processed_date is None) or (last_status == "NEVER_RUN")
    if is_full_load:
        logger.info("Running FULL LOAD (first incremental run or NEVER_RUN).")
    else:
        logger.info(f"Running INCREMENTAL load for orders after {last_processed_date}.")

    # --- STEP 1: EXTRACTION ---

    logger.info("=" * 60)
    logger.info("STEP 1/4 - EXTRACTION")
    logger.info("=" * 60)

    # Filtered extraction for orders
    if is_full_load:
        orders_df = read_table("orders")
    else:
        orders_df = read_table(
            "orders",
            predicate=f"orderDate > '{last_processed_date}'"
        )

    if orders_df.count() == 0 and not is_full_load:
        logger.info("No new orders found since watermark. Nothing to process.")
        update_watermark(last_processed_date, "SUCCEEDED")
        raise NormalExit()

    # Extract orderdetails only for relevant orders
    order_numbers = [row["orderNumber"] for row in orders_df.select("orderNumber").collect()]

    if len(order_numbers) <= 100:
        in_clause = ",".join(str(n) for n in order_numbers)
        orderdetails_df = read_table(
            "orderdetails",
            predicate=f"orderNumber IN ({in_clause})"
        )
    else:
        # For large sets, extract all and filter with Spark
        orderdetails_df = read_table("orderdetails")
        orderdetails_df = orderdetails_df.join(
            orders_df.select("orderNumber"),
            "orderNumber",
            "inner"
        )

    # Dimensions: full reload (Option A — acceptable for small volume)
    customers_df = read_table("customers")
    products_df = read_table("products")
    offices_df = read_table("offices")
    employees_df = read_table("employees")

    logger.info("Extraction complete.")

    # --- STEP 2: TRANSFORMATION ---

    logger.info("=" * 60)
    logger.info("STEP 2/4 - TRANSFORMATION (star schema)")
    logger.info("=" * 60)

    logger.info("Building dim_customers...")
    dim_customers = customers_df.select(
        F.col("customerNumber").alias("customer_id"),
        F.col("customerName").alias("customer_name"),
        F.concat_ws(" ", F.col("contactFirstName"), F.col("contactLastName")).alias("contact_name"),
        F.col("city"),
        F.col("country")
    )

    logger.info("Building dim_products...")
    dim_products = products_df.select(
        F.col("productCode").alias("product_id"),
        F.col("productName").alias("product_name"),
        F.col("productLine").alias("product_line"),
        F.col("productVendor").alias("product_vendor")
    )

    logger.info("Building dim_dates...")
    dim_dates = orders_df.select(
        F.col("orderDate")
    ).distinct().select(
        F.date_format("orderDate", "yyyyMMdd").cast(IntegerType()).alias("date_key"),
        F.col("orderDate").alias("full_date"),
        F.year("orderDate").alias("year"),
        F.quarter("orderDate").alias("quarter"),
        F.month("orderDate").alias("month"),
        F.dayofmonth("orderDate").alias("day")
    )

    # For dim_dates in incremental mode, we need to merge with existing dates.
    # Since we use Option A for dimensions (full reload), in incremental mode
    # dim_dates only contains new dates. We reload ALL orders for dim_dates.
    if not is_full_load:
        logger.info("Reloading all orders for complete dim_dates...")
        all_orders_for_dates = read_table("orders")
        dim_dates = all_orders_for_dates.select(
            F.col("orderDate")
        ).distinct().select(
            F.date_format("orderDate", "yyyyMMdd").cast(IntegerType()).alias("date_key"),
            F.col("orderDate").alias("full_date"),
            F.year("orderDate").alias("year"),
            F.quarter("orderDate").alias("quarter"),
            F.month("orderDate").alias("month"),
            F.dayofmonth("orderDate").alias("day")
        )

    logger.info("Building dim_countries...")
    customer_territory = (
        customers_df
        .join(employees_df, customers_df.salesRepEmployeeNumber == employees_df.employeeNumber, "left")
        .join(offices_df, employees_df.officeCode == offices_df.officeCode, "left")
        .select(
            customers_df.country,
            offices_df.territory
        )
        .distinct()
    )

    office_territories = offices_df.select("country", "territory").distinct()
    all_territories = customer_territory.unionByName(office_territories).distinct()

    dim_countries = all_territories.select(
        F.md5(F.col("country")).alias("country_key"),
        F.col("country"),
        F.coalesce(F.col("territory"), F.lit("N/A")).alias("territory")
    ).dropDuplicates(["country"])

    logger.info("Building fact_orders...")
    fact_orders = (
        orderdetails_df
        .join(orders_df, "orderNumber")
        .join(customers_df, "customerNumber", "left")
        .select(
            F.col("orderNumber").alias("order_id"),
            F.col("customerNumber").alias("customer_id"),
            F.col("productCode").alias("product_id"),
            F.date_format("orderDate", "yyyyMMdd").cast(IntegerType()).alias("order_date_key"),
            F.md5(F.col("country")).alias("country_key"),
            F.col("quantityOrdered").alias("quantity_ordered"),
            F.col("priceEach").alias("price_each"),
            (F.col("quantityOrdered") * F.col("priceEach")).alias("sales_amount"),
            # Partition columns
            F.year("orderDate").cast(IntegerType()).alias("order_year"),
            F.month("orderDate").cast(IntegerType()).alias("order_month"),
        )
    )

    # Compute the max orderDate from this delta for watermark update
    max_order_date_row = orders_df.agg(F.max("orderDate").alias("max_date")).collect()[0]
    new_max_date = max_order_date_row["max_date"]
    logger.info(f"Max orderDate in this batch: {new_max_date}")

    logger.info("Transformation complete.")

    # --- STEP 3: LOAD ---

    logger.info("=" * 60)
    logger.info("STEP 3/4 - LOAD (Parquet to S3)")
    logger.info("=" * 60)

    # fact_orders: partitioned write with dynamic overwrite
    fact_output = f"{s3_output}/fact_orders"

    if not is_full_load:
        logger.info("Merging new fact orders with existing partitions to avoid data loss...")
        try:
            affected_partitions = fact_orders.select("order_year", "order_month").distinct().collect()
            existing_dfs = []
            for row in affected_partitions:
                y = row["order_year"]
                m = row["order_month"]
                part_path = f"{fact_output}/order_year={y}/order_month={m}"
                try:
                    existing_df = spark.read.parquet(part_path)
                    existing_df = existing_df.withColumn("order_year", F.lit(y).cast(IntegerType())) \
                                             .withColumn("order_month", F.lit(m).cast(IntegerType()))
                    existing_dfs.append(existing_df)
                    logger.info(f"Loaded existing partition data from: {part_path}")
                except Exception as part_err:
                    logger.info(f"No existing partition found or error reading from {part_path}: {part_err}")

            if existing_dfs:
                from functools import reduce
                existing_all = reduce(lambda a, b: a.unionByName(b), existing_dfs)
                
                # Exclude matching keys (order_id, product_id) from the existing data
                delta_keys = fact_orders.select("order_id", "product_id").distinct()
                existing_filtered = existing_all.join(delta_keys, ["order_id", "product_id"], "left_anti")
                
                # Combine the remaining old records with the new delta
                fact_orders = existing_filtered.unionByName(fact_orders)
                logger.info("Successfully merged delta records with existing partition data.")
        except Exception as merge_err:
            logger.error(f"Error during incremental merge: {merge_err}", exc_info=True)
            raise

    logger.info(f"Writing fact_orders -> {fact_output} (partitioned by order_year, order_month)")
    fact_orders.write \
        .mode("overwrite") \
        .partitionBy("order_year", "order_month") \
        .parquet(fact_output)
    logger.info("  -> fact_orders: done")

    # Dimensions: full overwrite
    dimension_tables = {
        "dim_customers": dim_customers,
        "dim_products": dim_products,
        "dim_dates": dim_dates,
        "dim_countries": dim_countries,
    }

    for name, df in dimension_tables.items():
        output_path = f"{s3_output}/{name}"
        logger.info(f"Writing {name} -> {output_path}")
        df.write.mode("overwrite").parquet(output_path)
        logger.info(f"  -> {name}: done")

    logger.info("Load complete.")

    # --- STEP 4: UPDATE WATERMARK ---

    logger.info("=" * 60)
    logger.info("STEP 4/4 - UPDATE WATERMARK")
    logger.info("=" * 60)

    update_watermark(new_max_date, "SUCCEEDED")

    logger.info("=" * 60)
    logger.info("INCREMENTAL ETL PIPELINE COMPLETED SUCCESSFULLY")
    logger.info("=" * 60)

except NormalExit:
    logger.info("NormalExit caught. Exiting cleanly without error.")
except Exception as e:
    logger.error(f"ETL pipeline failed: {e}", exc_info=True)
    try:
        update_watermark(None, "FAILED")
    except Exception as wm_err:
        logger.error(f"Failed to update watermark on error: {wm_err}", exc_info=True)
    raise

finally:
    job.commit()
