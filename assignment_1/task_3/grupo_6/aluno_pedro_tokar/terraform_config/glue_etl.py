import sys
from awsglue.transforms import *
from awsglue.dynamicframe import DynamicFrame
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from awsglue.context import GlueContext
from awsglue.job import Job
from pyspark.sql.functions import col, year, quarter, month, dayofmonth

args = getResolvedOptions(sys.argv, ["JOB_NAME", "TARGET_S3_PATH", "GLUE_DATABASE"])
sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)
job.init(args["JOB_NAME"], args)

output_path = args["TARGET_S3_PATH"]
glue_db = args["GLUE_DATABASE"]
db_table_prefix = "classicmodels."

def read_mysql_table(table_name):
    return glueContext.create_dynamic_frame.from_options(
        connection_type="mysql",
        connection_options={
            "useConnectionProperties": "true",
            "dbtable": table_name,
            "connectionName": "classicmodels_rds_connection"
        }
    ).toDF()

df_orders = read_mysql_table("orders")
df_orderdetails = read_mysql_table("orderdetails")
df_customers = read_mysql_table("customers")
df_products = read_mysql_table("products")
df_offices = read_mysql_table("offices")

# dim_customers
dim_customers = df_customers.select(
    col("customerNumber").alias("customer_id"),
    col("customerName").alias("customer_name"),
    col("contactLastName").alias("contact_name"),
    col("city"),
    col("country")
)

# dim_products
dim_products = df_products.select(
    col("productCode").alias("product_id"),
    col("productName").alias("product_name"),
    col("productLine").alias("product_line"),
    col("productVendor").alias("product_vendor")
)

# dim_dates
dim_dates = df_orders.select(
    col("orderDate").alias("full_date")
).distinct()

dim_dates = dim_dates.select(
    col("full_date").alias("date_key"),
    col("full_date"),
    year("full_date").alias("year"),
    quarter("full_date").alias("quarter"),
    month("full_date").alias("month"),
    dayofmonth("full_date").alias("day")
)

# dim_countries
dim_countries = df_customers.select("country").distinct().union(df_offices.select("country").distinct()).distinct()
dim_countries = dim_countries.withColumn("country_key", col("country"))
dim_countries = dim_countries.select("country_key", "country")
dim_countries = dim_countries.withColumn("territory", col("country"))

# fact_orders
fact_orders = df_orderdetails.join(df_orders, "orderNumber")
fact_orders = fact_orders.join(df_customers, "customerNumber")

fact_orders = fact_orders.withColumn("sales_amount", col("quantityOrdered") * col("priceEach"))

fact_orders = fact_orders.select(
    col("orderNumber").alias("order_id"),
    col("customerNumber").alias("customer_id"),
    col("productCode").alias("product_id"),
    col("orderDate").alias("order_date_key"),
    col("country").alias("country_key"),
    col("quantityOrdered").alias("quantity_ordered"),
    col("priceEach").alias("price_each"),
    col("sales_amount")
)

def write_parquet(df, folder_name):
    dyf = DynamicFrame.fromDF(df, glueContext, "dyf_" + folder_name)
    
    sink = glueContext.getSink(
        path=output_path + folder_name + "/",
        connection_type="s3",
        updateBehavior="UPDATE_IN_DATABASE",
        partitionKeys=[],
        enableUpdateCatalog=True,
        transformation_ctx="ctx_" + folder_name
    )
    sink.setFormat("glueparquet")
    sink.setCatalogInfo(catalogDatabase=glue_db, catalogTableName=folder_name)
    sink.writeFrame(dyf)

write_parquet(fact_orders, "fact_orders")
write_parquet(dim_customers, "dim_customers")
write_parquet(dim_products, "dim_products")
write_parquet(dim_dates, "dim_dates")
write_parquet(dim_countries, "dim_countries")

job.commit()
