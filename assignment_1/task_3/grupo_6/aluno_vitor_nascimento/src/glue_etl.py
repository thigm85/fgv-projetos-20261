import sys
from awsglue.transforms import *
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from awsglue.context import GlueContext
from awsglue.job import Job
from pyspark.sql.functions import col, concat, lit, year, quarter, month, dayofmonth

args = getResolvedOptions(sys.argv, ['JOB_NAME', 'S3_OUTPUT_PATH', 'RDS_CONNECTION_NAME', 'DB_NAME'])

sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)
job.init(args['JOB_NAME'], args)

s3_output = args['S3_OUTPUT_PATH']
connection_name = args['RDS_CONNECTION_NAME']
db_name = args['DB_NAME']

def read_table(table_name):
    return glueContext.create_dynamic_frame.from_options(
        connection_type="mysql",
        connection_options={
            "useConnectionProperties": "true",
            "dbtable": f"{db_name}.{table_name}",
            "connectionName": connection_name,
        }
    ).toDF()

customers = read_table("customers")
products = read_table("products")
orders = read_table("orders")
order_details = read_table("orderdetails")

dim_customers = customers.select(
    col("customerNumber").alias("customer_id"),
    col("customerName").alias("customer_name"),
    concat(col("contactFirstName"), lit(" "), col("contactLastName")).alias("contact_name"),
    col("city"),
    col("country")
)

dim_products = products.select(
    col("productCode").alias("product_id"),
    col("productName").alias("product_name"),
    col("productLine").alias("product_line"),
    col("productVendor").alias("product_vendor")
)

dim_countries = customers.select("country").distinct() \
    .select(
        col("country").alias("country_key"),
        col("country"),
        lit("Unknown").alias("territory")
    )

dim_dates = orders.select(col("orderDate").alias("full_date")).distinct() \
    .select(
        col("full_date").alias("date_key"),
        "full_date",
        year("full_date").alias("year"),
        quarter("full_date").alias("quarter"),
        month("full_date").alias("month"),
        dayofmonth("full_date").alias("day")
    )

fact_orders = orders.join(order_details, "orderNumber") \
    .join(customers.select("customerNumber", "country"), "customerNumber") \
    .select(
        col("orderNumber").alias("order_id"),
        col("customerNumber").alias("customer_id"),
        col("productCode").alias("product_id"),
        col("orderDate").alias("order_date_key"),
        col("country").alias("country_key"),
        col("quantityOrdered").alias("quantity_ordered"),
        col("priceEach").alias("price_each"),
        (col("quantityOrdered") * col("priceEach")).cast("decimal(10,2)").alias("sales_amount")
    )

def write_parquet(df, table_name):
    output_path = f"{s3_output}/{table_name}/"
    df.write.mode("overwrite").parquet(output_path)

write_parquet(fact_orders, "fact_orders")
write_parquet(dim_customers, "dim_customers")
write_parquet(dim_products, "dim_products")
write_parquet(dim_dates, "dim_dates")
write_parquet(dim_countries, "dim_countries")

job.commit()
