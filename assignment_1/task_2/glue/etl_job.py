"""
ETL Job — classicmodels → Star Schema (Parquet no S3)

Tabelas de saída:
  - fact_orders
  - dim_customers
  - dim_products
  - dim_dates
  - dim_countries
"""

import sys
from awsglue.transforms import *
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from awsglue.context import GlueContext
from awsglue.job import Job
from pyspark.sql import functions as F
from pyspark.sql.types import IntegerType, StringType, DateType

args = getResolvedOptions(sys.argv, [
    "JOB_NAME",
    "S3_OUTPUT_PATH",
    "JDBC_URL",
    "DB_USER",
    "DB_PASSWORD",
    "CONNECTION_NAME",
])

sc          = SparkContext()
glueContext = GlueContext(sc)
spark       = glueContext.spark_session
job         = Job(glueContext)
job.init(args["JOB_NAME"], args)

S3_OUTPUT  = args["S3_OUTPUT_PATH"].rstrip("/")
JDBC_URL   = args["JDBC_URL"]
DB_USER    = args["DB_USER"]
DB_PASSWORD = args["DB_PASSWORD"]

print(f"[INFO] S3 output path: {S3_OUTPUT}")
print(f"[INFO] JDBC URL: {JDBC_URL}")


def read_table(table_name: str):
    """Lê uma tabela do MySQL via JDBC e retorna um DataFrame Spark."""
    print(f"[INFO] Extraindo tabela: {table_name}")
    return (
        spark.read
        .format("jdbc")
        .option("url", JDBC_URL)
        .option("dbtable", table_name)
        .option("user", DB_USER)
        .option("password", DB_PASSWORD)
        .option("driver", "com.mysql.cj.jdbc.Driver")
        .load()
    )


def write_parquet(df, entity: str):
    """Grava um DataFrame como Parquet no S3, particionado por entidade."""
    output_path = f"{S3_OUTPUT}/{entity}/"
    print(f"[INFO] Gravando {entity} em {output_path} ({df.count()} linhas)")
    (
        df.coalesce(1)
        .write
        .mode("overwrite")
        .parquet(output_path)
    )
    print(f"[OK]   {entity} gravado com sucesso.")


orders_raw       = read_table("orders")
orderdetails_raw = read_table("orderdetails")
customers_raw    = read_table("customers")
products_raw     = read_table("products")

dim_customers = (
    customers_raw
    .select(
        F.col("customerNumber").cast(IntegerType()).alias("customer_id"),
        F.col("customerName").alias("customer_name"),
        F.concat_ws(" ", F.col("contactFirstName"), F.col("contactLastName")).alias("contact_name"),
        F.col("city"),
        F.col("country"),
    )
    .dropDuplicates(["customer_id"])
)

dim_products = (
    products_raw
    .select(
        F.col("productCode").alias("product_id"),
        F.col("productName").alias("product_name"),
        F.col("productLine").alias("product_line"),
        F.col("productVendor").alias("product_vendor"),
    )
    .dropDuplicates(["product_id"])
)

dim_countries = (
    customers_raw
    .select(
        F.col("country"),
        F.col("territory"),
    )
    .dropDuplicates(["country"])
    .withColumn(
        "country_key",
        F.dense_rank().over(
            __import__("pyspark.sql.window", fromlist=["Window"])
            .Window.orderBy("country")
        )
    )
    .select("country_key", "country", "territory")
)

order_dates = (
    orders_raw
    .select(F.col("orderDate").cast(DateType()).alias("full_date"))
    .dropDuplicates(["full_date"])
    .filter(F.col("full_date").isNotNull())
)

dim_dates = (
    order_dates
    .withColumn("date_key",  F.date_format(F.col("full_date"), "yyyyMMdd").cast(IntegerType()))
    .withColumn("year",      F.year(F.col("full_date")))
    .withColumn("quarter",   F.quarter(F.col("full_date")))
    .withColumn("month",     F.month(F.col("full_date")))
    .withColumn("day",       F.dayofmonth(F.col("full_date")))
    .select("date_key", "full_date", "year", "quarter", "month", "day")
    .orderBy("date_key")
)

orders_joined = (
    orders_raw
    .join(orderdetails_raw, on="orderNumber", how="inner")
)

fact_orders = (
    orders_joined
    .join(
        dim_countries.select("country", "country_key"),
        on=orders_joined["customerNumber"].cast(IntegerType()) ==
           customers_raw["customerNumber"].cast(IntegerType()),
        how="left",
    )
    .join(
        customers_raw.select("customerNumber", "country"),
        orders_joined["customerNumber"] == customers_raw["customerNumber"],
        how="left",
    )
    .join(
        dim_countries.select("country", "country_key"),
        on="country",
        how="left",
    )
    .select(
        F.col("orderNumber").cast(IntegerType()).alias("order_id"),
        orders_joined["customerNumber"].cast(IntegerType()).alias("customer_id"),
        F.col("productCode").alias("product_id"),
        F.date_format(
            F.col("orderDate").cast(DateType()), "yyyyMMdd"
        ).cast(IntegerType()).alias("order_date_key"),
        F.col("country_key"),
        F.col("quantityOrdered").cast(IntegerType()).alias("quantity_ordered"),
        F.col("priceEach").cast("decimal(10,2)").alias("price_each"),
        (
            F.col("quantityOrdered").cast(IntegerType()) *
            F.col("priceEach").cast("decimal(10,2)")
        ).alias("sales_amount"),
    )
    .dropDuplicates(["order_id", "product_id"])
)

write_parquet(fact_orders,   "fact_orders")
write_parquet(dim_customers, "dim_customers")
write_parquet(dim_products,  "dim_products")
write_parquet(dim_dates,     "dim_dates")
write_parquet(dim_countries, "dim_countries")

print("[INFO] ETL finalizado com sucesso!")
job.commit()