#!/usr/bin/env python3
import sys
import logging
import traceback
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from awsglue.context import GlueContext
from awsglue.job import Job
from pyspark.sql import functions as F
from pyspark.sql.window import Window
import boto3
import json

logger = logging.getLogger()
logger.setLevel(logging.INFO)

args = getResolvedOptions(sys.argv, ["JOB_NAME", "CONNECTION_NAME", "JDBC_URL", "DATABASE_NAME", "S3_OUTPUT_PATH", "AWS_REGION", "RDS_SECRET_ARN"])

sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)
job.init(args["JOB_NAME"], args)

def get_db_credentials(secret_arn: str, region: str):
    if not secret_arn:
        return None
    client = boto3.client("secretsmanager", region_name=region)
    resp = client.get_secret_value(SecretId=secret_arn)
    return json.loads(resp.get("SecretString", "{}"))

creds = get_db_credentials(args.get("RDS_SECRET_ARN"), args.get("AWS_REGION")) or {}
db_user = creds.get("username") or "admin"
db_password = creds.get("password") or "ClassicModels2024!"
output_path = args["S3_OUTPUT_PATH"]
jdbc_url = args["JDBC_URL"]

try:
    logger.info(f"Starting ETL: {args['JOB_NAME']}")
    
    logger.info("Extracting orders...")
    orders_df = spark.read.format("jdbc").option("url", jdbc_url).option("dbtable", "orders").option("user", db_user).option("password", db_password).option("driver", "com.mysql.cj.jdbc.Driver").load()
    
    logger.info("Extracting orderdetails...")
    orderdetails_df = spark.read.format("jdbc").option("url", jdbc_url).option("dbtable", "orderdetails").option("user", db_user).option("password", db_password).option("driver", "com.mysql.cj.jdbc.Driver").load()
    
    logger.info("Extracting customers...")
    customers_df = spark.read.format("jdbc").option("url", jdbc_url).option("dbtable", "customers").option("user", db_user).option("password", db_password).option("driver", "com.mysql.cj.jdbc.Driver").load()
    
    logger.info("Extracting products...")
    products_df = spark.read.format("jdbc").option("url", jdbc_url).option("dbtable", "products").option("user", db_user).option("password", db_password).option("driver", "com.mysql.cj.jdbc.Driver").load()
    
    logger.info("Extracting productlines...")
    productlines_df = spark.read.format("jdbc").option("url", jdbc_url).option("dbtable", "productlines").option("user", db_user).option("password", db_password).option("driver", "com.mysql.cj.jdbc.Driver").load()
    
    logger.info("Transforming to star schema...")
    
    dim_dates = orders_df.select(
        F.col("orderDate").cast("date").alias("full_date"),
        F.date_format(F.col("orderDate"), "yyyyMMdd").cast("int").alias("date_key"),
        F.year(F.col("orderDate")).alias("year"),
        F.quarter(F.col("orderDate")).alias("quarter"),
        F.month(F.col("orderDate")).alias("month"),
        F.dayofmonth(F.col("orderDate")).alias("day")
    ).dropna().distinct()
    
    dim_customers = customers_df.select(
        F.col("customerNumber").alias("customer_id"),
        F.col("customerName").alias("customer_name"),
        F.concat(F.col("contactFirstName"), F.lit(" "), F.col("contactLastName")).alias("contact_name"),
        F.col("city"),
        F.col("country")
    ).distinct()
    
    products_full = products_df.join(productlines_df, "productLine", "left")
    dim_products = products_full.select(F.col("productCode").alias("product_id"), F.col("productName").alias("product_name"), F.col("productLine").alias("product_line"), F.col("productVendor").alias("product_vendor")).distinct()
    
    dim_countries = customers_df.select(F.col("country")).distinct().withColumn(
        "country_key", F.row_number().over(Window.orderBy(F.col("country")))
    ).withColumn("territory", F.lit(None).cast("string"))
    
    orders_with_details = (
        orders_df.join(orderdetails_df, "orderNumber", "inner")
            .join(customers_df, "customerNumber", "inner")
            .join(products_df, "productCode", "inner")
    )

    orders_with_country = orders_with_details.join(
        dim_countries.select("country", "country_key"),
        "country",
        "left"
    )

    fact_orders = orders_with_country.withColumn(
        "order_date_key", F.date_format(F.col("orderDate"), "yyyyMMdd").cast("int")
    ).select(
        F.col("orderNumber").alias("order_id"),
        F.col("customerNumber").alias("customer_id"),
        F.col("productCode").alias("product_id"),
        F.col("order_date_key"),
        F.coalesce(F.col("country_key"), F.lit(0)).alias("country_key"),
        F.col("quantityOrdered").alias("quantity_ordered"),
        F.col("priceEach").cast("decimal(10,2)").alias("price_each"),
        (F.col("quantityOrdered") * F.col("priceEach")).cast("decimal(12,2)").alias("sales_amount")
    ).distinct()
    
    validation_count = fact_orders.where(F.col("sales_amount") != (F.col("quantity_ordered") * F.col("price_each"))).count()
    if validation_count == 0:
        logger.info("✓ sales_amount validation passed")
    else:
        logger.warning(f"⚠ {validation_count} rows with inconsistent sales_amount")
    
    logger.info("Writing to S3...")
    write_opts = {"mode": "overwrite", "compression": "snappy"}
    
    fact_orders.coalesce(1).write.parquet(f"{output_path}fact_orders/", **write_opts)
    dim_customers.coalesce(1).write.parquet(f"{output_path}dim_customers/", **write_opts)
    dim_products.coalesce(1).write.parquet(f"{output_path}dim_products/", **write_opts)
    dim_dates.coalesce(1).write.parquet(f"{output_path}dim_dates/", **write_opts)
    dim_countries.coalesce(1).write.parquet(f"{output_path}dim_countries/", **write_opts)
    
    logger.info(f"✓ ETL completed: fact_orders={fact_orders.count()}, dim_customers={dim_customers.count()}, dim_products={dim_products.count()}, dim_dates={dim_dates.count()}, dim_countries={dim_countries.count()}")
    job.commit()

except Exception as e:
    logger.error(f"✗ ETL failed: {str(e)}")
    logger.error(traceback.format_exc())
    job.commit()
    sys.exit(1)