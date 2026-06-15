import sys
from awsglue.transforms import *
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from awsglue.context import GlueContext
from awsglue.job import Job
from pyspark.sql.functions import col, year, month, dayofmonth, quarter

# CONFIGURAÇÃO DO JOB
args = getResolvedOptions(sys.argv, ['JOB_NAME'])
sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)
job.init(args['JOB_NAME'], args)

# EXTRAÇÃO
jdbc_url = "jdbc:mysql://xxxxx.us-east-1.rds.amazonaws.com:3306/classicmodels"
properties = {
    "user": "admin",
    "password": "SUA_SENHA_REAL",  
    "driver": "com.mysql.cj.jdbc.Driver"
}

# Lendo as tabelas do MySQL
orders = spark.read.jdbc(jdbc_url, "orders", properties=properties)
orderdetails = spark.read.jdbc(jdbc_url, "orderdetails", properties=properties)
customers = spark.read.jdbc(jdbc_url, "customers", properties=properties)
products = spark.read.jdbc(jdbc_url, "products", properties=properties)

# FACT TABLE
fact_orders = orderdetails.join(orders, "orderNumber") \
    .select(
        col("orderNumber").alias("order_id"),
        col("productCode").alias("product_id"),
        col("quantityOrdered").alias("quantity_ordered"),
        col("priceEach").alias("price_each"),
        (col("quantityOrdered") * col("priceEach")).alias("sales_amount")
    )

# DIM CUSTOMERS
dim_customers = customers.select(
    col("customerNumber").alias("customer_id"),
    col("customerName").alias("customer_name"),
    col("contactFirstName").alias("contact_name"),
    col("city"),
    col("country")
)

# DIM PRODUCTS
dim_products = products.select(
    col("productCode").alias("product_id"),
    col("productName").alias("product_name"),
    col("productLine").alias("product_line"),
    col("productVendor").alias("product_vendor")
)

# DIM DATES - Versão corrigida (agora antes de salvar)
dim_dates = orders.select("orderDate").distinct() \
    .withColumn("date_id", col("orderDate").cast("string")) \
    .withColumn("year", year("orderDate")) \
    .withColumn("month", month("orderDate")) \
    .withColumn("day", dayofmonth("orderDate")) \
    .withColumn("quarter", quarter("orderDate")) \
    .select(
        col("date_id"),
        col("orderDate").alias("full_date"),
        col("year"),
        col("month"),
        col("day"),
        col("quarter")
    )

# LOAD (S3 - PARQUET)
output_path = "s3://classicmodels-data-lake-g4-b888b1e7/"

fact_orders.write.mode("overwrite").parquet(output_path + "fact_orders/")
dim_customers.write.mode("overwrite").parquet(output_path + "dim_customers/")
dim_products.write.mode("overwrite").parquet(output_path + "dim_products/")
dim_dates.write.mode("overwrite").parquet(output_path + "dim_dates/")

# FINALIZAR JOB
job.commit()
