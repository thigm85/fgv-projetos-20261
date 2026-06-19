import sys
from awsglue.transforms import *
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from pyspark.sql.functions import *
from pyspark.sql.types import *
from awsglue.context import GlueContext
from awsglue.job import Job

# Get job arguments
args = getResolvedOptions(sys.argv, [
    'JOB_NAME',
    'rds_endpoint',
    'db_name',
    'db_user',
    'db_password',
    's3_output_path'
])

# Initialize contexts
sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)
job.init(args['JOB_NAME'], args)

# Database connection details
rds_endpoint = args['rds_endpoint']
db_name = args['db_name']
db_user = args['db_user']
db_password = args['db_password']
s3_output_path = args['s3_output_path']

# JDBC URL for MySQL
jdbc_url = f"jdbc:mysql://{rds_endpoint}:3306/{db_name}"

# Connection properties
connection_properties = {
    "user": db_user,
    "password": db_password,
    "driver": "com.mysql.jdbc.Driver"
}

# Extract data from S3 CSVs instead of RDS
print("Extracting data from S3 CSVs...")

# Read source tables from S3 CSVs
customers_df = spark.read.csv(f"{s3_output_path}../raw/customers.csv", header=True, inferSchema=True)
products_df = spark.read.csv(f"{s3_output_path}../raw/products.csv", header=True, inferSchema=True)
productlines_df = spark.read.csv(f"{s3_output_path}../raw/productlines.csv", header=True, inferSchema=True)
orders_df = spark.read.csv(f"{s3_output_path}../raw/orders.csv", header=True, inferSchema=True)
orderdetails_df = spark.read.csv(f"{s3_output_path}../raw/orderdetails.csv", header=True, inferSchema=True)
offices_df = spark.read.csv(f"{s3_output_path}../raw/offices.csv", header=True, inferSchema=True)

print("Data extraction completed.")

# Transform to Star Schema
print("Transforming to star schema...")

# DIM_CUSTOMERS
dim_customers = customers_df.select(
    col("customerNumber").alias("customer_id"),
    col("customerName").alias("customer_name"),
    concat(col("contactFirstName"), lit(" "), col("contactLastName")).alias("contact_name"),
    col("city"),
    col("country")
)

# DIM_PRODUCTS
dim_products = products_df.join(productlines_df, "productLine", "left").select(
    col("productCode").alias("product_id"),
    col("productName").alias("product_name"),
    col("productLine").alias("product_line"),
    col("productVendor").alias("product_vendor")
)

# DIM_DATES
# Create date dimension from orders
dates_df = orders_df.select("orderDate").distinct()
dim_dates = dates_df.select(
    date_format(col("orderDate"), "yyyyMMdd").cast("int").alias("date_key"),
    col("orderDate").alias("full_date"),
    year(col("orderDate")).alias("year"),
    quarter(col("orderDate")).alias("quarter"),
    month(col("orderDate")).alias("month"),
    dayofmonth(col("orderDate")).alias("day")
).distinct()

# DIM_COUNTRIES
# Create country dimension from customers and offices
countries_from_customers = customers_df.select("country").distinct()
countries_from_offices = offices_df.select("country").distinct()
all_countries = countries_from_customers.union(countries_from_offices).distinct()

dim_countries = all_countries.withColumn("country_key", monotonically_increasing_id() + 1) \
    .select(
        col("country_key"),
        col("country"),
        lit("N/A").alias("territory")  # Simplified, could be enhanced
    )

# FACT_ORDERS
# Join orderdetails with orders, customers, and products
fact_orders_base = orderdetails_df \
    .join(orders_df, "orderNumber") \
    .join(customers_df, "customerNumber") \
    .join(products_df, "productCode")

# Add surrogate keys
fact_orders_with_keys = fact_orders_base \
    .join(dim_countries, fact_orders_base["country"] == dim_countries["country"], "left") \
    .withColumn("order_date_key", date_format(col("orderDate"), "yyyyMMdd").cast("int"))

fact_orders = fact_orders_with_keys.select(
    col("orderNumber").alias("order_id"),
    col("customerNumber").alias("customer_id"),
    col("productCode").alias("product_id"),
    col("order_date_key"),
    col("country_key"),
    col("quantityOrdered").alias("quantity_ordered"),
    col("priceEach").alias("price_each"),
    (col("quantityOrdered") * col("priceEach")).alias("sales_amount")
)

print("Transformation completed.")

# Load to S3 in Parquet format
print("Loading data to S3...")

# Write fact table
fact_orders.write.mode("overwrite").parquet(f"{s3_output_path}fact_orders/")

# Write dimension tables
dim_customers.write.mode("overwrite").parquet(f"{s3_output_path}dim_customers/")
dim_products.write.mode("overwrite").parquet(f"{s3_output_path}dim_products/")
dim_dates.write.mode("overwrite").parquet(f"{s3_output_path}dim_dates/")
dim_countries.write.mode("overwrite").parquet(f"{s3_output_path}dim_countries/")

print("Data loading completed.")

# Commit job
job.commit()
print("ETL job completed successfully!")