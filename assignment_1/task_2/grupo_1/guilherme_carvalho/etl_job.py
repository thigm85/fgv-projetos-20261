import sys
import logging
from awsglue.transforms import *
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from awsglue.context import GlueContext
from awsglue.job import Job
from pyspark.sql import functions as F
from pyspark.sql.types import IntegerType

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("etl_job")

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

s3_output = args["S3_OUTPUT_PATH"]
jdbc_url = args["JDBC_CONNECTION_URL"]
db_user = args["DB_USER"]
db_password = args["DB_PASSWORD"]
db_name = args["DB_NAME"]

connection_options = {
    "url": jdbc_url,
    "user": db_user,
    "password": db_password,
}


def read_table(table_name):
    logger.info(f"Extracting table: {db_name}.{table_name}")
    df = spark.read.format("jdbc").options(
        **connection_options,
        dbtable=f"{db_name}.{table_name}"
    ).load()
    row_count = df.count()
    logger.info(f"  -> {table_name}: {row_count} rows extracted")
    if row_count == 0:
        logger.warning(f"  -> WARNING: {table_name} is empty!")
    return df


# --- EXTRACTION ---

logger.info("=" * 50)
logger.info("STEP 1/3 - EXTRACTION")
logger.info("=" * 50)

customers_df = read_table("customers")
products_df = read_table("products")
orders_df = read_table("orders")
orderdetails_df = read_table("orderdetails")
offices_df = read_table("offices")
employees_df = read_table("employees")

logger.info("Extraction complete.")

# --- TRANSFORMATION ---

logger.info("=" * 50)
logger.info("STEP 2/3 - TRANSFORMATION (star schema)")
logger.info("=" * 50)

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
    .join(customers_df, orders_df.customerNumber == customers_df.customerNumber, "left")
    .select(
        F.col("orderNumber").alias("order_id"),
        orders_df.customerNumber.alias("customer_id"),
        F.col("productCode").alias("product_id"),
        F.date_format("orderDate", "yyyyMMdd").cast(IntegerType()).alias("order_date_key"),
        F.md5(customers_df.country).alias("country_key"),
        F.col("quantityOrdered").alias("quantity_ordered"),
        F.col("priceEach").alias("price_each"),
        (F.col("quantityOrdered") * F.col("priceEach")).alias("sales_amount")
    )
)

logger.info("Transformation complete.")

# --- LOAD ---

logger.info("=" * 50)
logger.info("STEP 3/3 - LOAD (Parquet to S3)")
logger.info("=" * 50)

tables = {
    "fact_orders": fact_orders,
    "dim_customers": dim_customers,
    "dim_products": dim_products,
    "dim_dates": dim_dates,
    "dim_countries": dim_countries,
}

for name, df in tables.items():
    output_path = f"{s3_output}/{name}"
    logger.info(f"Writing {name} -> {output_path}")
    df.write.mode("overwrite").parquet(output_path)
    logger.info(f"  -> {name}: done")

logger.info("=" * 50)
logger.info("ETL PIPELINE COMPLETED SUCCESSFULLY")
logger.info("=" * 50)

job.commit()
