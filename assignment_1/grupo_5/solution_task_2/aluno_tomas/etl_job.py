from __future__ import annotations

import sys

from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from pyspark.sql import functions as F
from pyspark.sql.window import Window


args = getResolvedOptions(sys.argv, ["JOB_NAME", "S3_TARGET_PATH", "CONNECTION_NAME"])
sc = SparkContext()
glue_context = GlueContext(sc)
spark = glue_context.spark_session
job = Job(glue_context)
job.init(args["JOB_NAME"], args)

S3_TARGET_PATH = args["S3_TARGET_PATH"].rstrip("/")
CONNECTION_NAME = args["CONNECTION_NAME"]


def read_mysql_table(table_name):
    frame = glue_context.create_dynamic_frame.from_options(
        connection_type="mysql",
        connection_options={
            "useConnectionProperties": "true",
            "connectionName": CONNECTION_NAME,
            "dbtable": table_name,
        },
    )
    return frame.toDF()


customers = read_mysql_table("customers")
products = read_mysql_table("products")
productlines = read_mysql_table("productlines")
orders = read_mysql_table("orders")
orderdetails = read_mysql_table("orderdetails")
employees = read_mysql_table("employees")
offices = read_mysql_table("offices")

customers_with_territory = (
    customers.alias("c")
    .join(employees.select("employeeNumber", "officeCode").alias("e"), F.col("c.salesRepEmployeeNumber") == F.col("e.employeeNumber"), "left")
    .join(offices.select("officeCode", "territory").alias("o"), F.col("e.officeCode") == F.col("o.officeCode"), "left")
)

dim_customers = customers.select(
    F.col("customerNumber").cast("int").alias("customer_id"),
    F.col("customerName").alias("customer_name"),
    F.concat_ws(" ", F.col("contactFirstName"), F.col("contactLastName")).alias("contact_name"),
    F.col("city"),
    F.col("country"),
).dropDuplicates(["customer_id"])

dim_products = products.select(
    F.col("productCode").alias("product_id"),
    F.col("productName").alias("product_name"),
    F.col("productLine").alias("product_line"),
    F.col("productVendor").alias("product_vendor"),
).dropDuplicates(["product_id"])

dim_dates = (
    orders.select(F.to_date("orderDate").alias("full_date"))
    .where(F.col("full_date").isNotNull())
    .dropDuplicates(["full_date"])
    .select(
        F.date_format("full_date", "yyyyMMdd").cast("int").alias("date_key"),
        F.col("full_date"),
        F.year("full_date").alias("year"),
        F.quarter("full_date").alias("quarter"),
        F.month("full_date").alias("month"),
        F.dayofmonth("full_date").alias("day"),
    )
)

dim_countries = (
    customers_with_territory.select(
        F.col("c.country").alias("country"),
        F.coalesce(F.col("o.territory"), F.lit("Unknown")).alias("territory"),
    )
    .where(F.col("country").isNotNull())
    .groupBy("country")
    .agg(F.min("territory").alias("territory"))
    .select(
        F.dense_rank().over(Window.orderBy("country")).cast("int").alias("country_key"),
        F.col("country"),
        F.col("territory"),
    )
)

fact_orders = (
    orderdetails.alias("od")
    .join(orders.alias("o"), F.col("od.orderNumber") == F.col("o.orderNumber"), "inner")
    .join(customers.alias("c"), F.col("o.customerNumber") == F.col("c.customerNumber"), "inner")
    .withColumn("order_date_key", F.date_format(F.to_date("o.orderDate"), "yyyyMMdd").cast("int"))
    .join(dim_dates.select("date_key"), F.col("order_date_key") == F.col("date_key"), "inner")
    .join(dim_countries.alias("dc"), F.col("c.country") == F.col("dc.country"), "inner")
    .select(
        F.col("o.orderNumber").cast("int").alias("order_id"),
        F.col("o.customerNumber").cast("int").alias("customer_id"),
        F.col("od.productCode").alias("product_id"),
        F.col("order_date_key"),
        F.col("dc.country_key").cast("int").alias("country_key"),
        F.col("od.quantityOrdered").cast("int").alias("quantity_ordered"),
        F.col("od.priceEach").cast("decimal(18,2)").alias("price_each"),
        (F.col("od.quantityOrdered").cast("decimal(18,2)") * F.col("od.priceEach").cast("decimal(18,2)")).cast("decimal(18,2)").alias("sales_amount"),
    )
)


def write_table(df, table_name: str) -> None:
    path = f"{S3_TARGET_PATH}/{table_name}/"
    df.write.mode("overwrite").parquet(path)
    print(f"Saved {table_name} to {path}")


write_table(fact_orders, "fact_orders")
write_table(dim_customers, "dim_customers")
write_table(dim_products, "dim_products")
write_table(dim_dates, "dim_dates")
write_table(dim_countries, "dim_countries")

job.commit()

