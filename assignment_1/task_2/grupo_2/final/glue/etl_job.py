import sys

from awsglue.job import Job
from awsglue.transforms import *  # noqa: F401,F403
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from pyspark.sql import DataFrame
from pyspark.sql import functions as F
from awsglue.context import GlueContext


def read_table(glue_context: GlueContext, jdbc_url: str, dbtable: str, user: str, password: str) -> DataFrame:
    return (
        glue_context.spark_session.read.format("jdbc")
        .option("url", jdbc_url)
        .option("dbtable", dbtable)
        .option("user", user)
        .option("password", password)
        .option("driver", "com.mysql.cj.jdbc.Driver")
        .load()
    )


def write_parquet(df: DataFrame, bucket: str, prefix: str, table_name: str) -> None:
    output_path = f"s3://{bucket}/{prefix}/{table_name}/"
    df.write.mode("overwrite").parquet(output_path)


def require_non_empty(df: DataFrame, table_name: str) -> None:
    if df.limit(1).count() == 0:
        raise RuntimeError(f"{table_name} is empty")


def ensure_no_orphans(fact_df: DataFrame, dim_customers: DataFrame, dim_products: DataFrame, dim_dates: DataFrame, dim_countries: DataFrame) -> None:
    customer_orphans = (
        fact_df.join(dim_customers.select("customer_id"), on="customer_id", how="left_anti").count()
    )
    product_orphans = (
        fact_df.join(dim_products.select("product_id"), on="product_id", how="left_anti").count()
    )
    date_orphans = (
        fact_df.join(dim_dates.select("date_key"), fact_df.order_date_key == dim_dates.date_key, "left_anti").count()
    )
    country_orphans = (
        fact_df.join(dim_countries.select("country_key"), on="country_key", how="left_anti").count()
    )

    if any([customer_orphans, product_orphans, date_orphans, country_orphans]):
        raise RuntimeError(
            "Referential integrity validation failed: "
            f"customer_orphans={customer_orphans}, "
            f"product_orphans={product_orphans}, "
            f"date_orphans={date_orphans}, "
            f"country_orphans={country_orphans}"
        )


def ensure_sales_amount(df: DataFrame) -> None:
    invalid_rows = (
        df.filter(
            F.col("sales_amount")
            != F.round(F.col("quantity_ordered").cast("double") * F.col("price_each").cast("double"), 2)
        ).count()
    )
    if invalid_rows > 0:
        raise RuntimeError(f"sales_amount validation failed for {invalid_rows} rows")


args = getResolvedOptions(
    sys.argv,
    [
        "JOB_NAME",
        "db_host",
        "db_port",
        "db_name",
        "db_user",
        "db_password",
        "output_bucket",
        "output_prefix",
    ],
)

sc = SparkContext()
glue_context = GlueContext(sc)
spark = glue_context.spark_session
job = Job(glue_context)
job.init(args["JOB_NAME"], args)

jdbc_url = f"jdbc:mysql://{args['db_host']}:{args['db_port']}/{args['db_name']}"

orders = read_table(glue_context, jdbc_url, "orders", args["db_user"], args["db_password"])
orderdetails = read_table(glue_context, jdbc_url, "orderdetails", args["db_user"], args["db_password"])
customers = read_table(glue_context, jdbc_url, "customers", args["db_user"], args["db_password"])
products = read_table(glue_context, jdbc_url, "products", args["db_user"], args["db_password"])
employees = read_table(glue_context, jdbc_url, "employees", args["db_user"], args["db_password"])
offices = read_table(glue_context, jdbc_url, "offices", args["db_user"], args["db_password"])

customer_locations = (
    customers.alias("c")
    .join(
        employees.select(
            F.col("employeeNumber").alias("employee_number"),
            F.col("officeCode").alias("office_code"),
        ).alias("e"),
        F.col("c.salesRepEmployeeNumber") == F.col("e.employee_number"),
        "left",
    )
    .join(
        offices.select(
            F.col("officeCode").alias("office_code"),
            F.col("territory").alias("territory"),
        ).alias("o"),
        F.col("e.office_code") == F.col("o.office_code"),
        "left",
    )
    .select(
        F.col("c.customerNumber").alias("customer_id"),
        F.col("c.customerName").alias("customer_name"),
        F.concat_ws(" ", F.col("c.contactFirstName"), F.col("c.contactLastName")).alias("contact_name"),
        F.col("c.city").alias("city"),
        F.trim(F.col("c.country")).alias("country"),
        F.coalesce(F.col("o.territory"), F.lit("Unknown")).alias("territory"),
    )
)

dim_customers = customer_locations.select(
    "customer_id",
    "customer_name",
    "contact_name",
    "city",
    "country",
).dropDuplicates(["customer_id"])

dim_products = products.select(
    F.col("productCode").alias("product_id"),
    F.col("productName").alias("product_name"),
    F.col("productLine").alias("product_line"),
    F.col("productVendor").alias("product_vendor"),
).dropDuplicates(["product_id"])

dim_dates = (
    orders.select(F.col("orderDate").alias("full_date"))
    .dropDuplicates(["full_date"])
    .withColumn("date_key", F.date_format("full_date", "yyyyMMdd").cast("int"))
    .withColumn("year", F.year("full_date"))
    .withColumn("quarter", F.quarter("full_date"))
    .withColumn("month", F.month("full_date"))
    .withColumn("day", F.dayofmonth("full_date"))
    .select("date_key", "full_date", "year", "quarter", "month", "day")
)

dim_countries = (
    customer_locations.select("country", "territory")
    .dropDuplicates(["country", "territory"])
    .withColumn("country_key", F.sha2(F.concat_ws("|", F.col("country"), F.col("territory")), 256))
    .select("country_key", "country", "territory")
)

fact_orders = (
    orders.alias("o")
    .join(orderdetails.alias("od"), F.col("o.orderNumber") == F.col("od.orderNumber"), "inner")
    .join(customer_locations.alias("cl"), F.col("o.customerNumber") == F.col("cl.customer_id"), "inner")
    .select(
        F.col("o.orderNumber").alias("order_id"),
        F.col("o.customerNumber").alias("customer_id"),
        F.col("od.productCode").alias("product_id"),
        F.date_format(F.col("o.orderDate"), "yyyyMMdd").cast("int").alias("order_date_key"),
        F.sha2(F.concat_ws("|", F.col("cl.country"), F.col("cl.territory")), 256).alias("country_key"),
        F.col("od.quantityOrdered").alias("quantity_ordered"),
        F.round(F.col("od.priceEach"), 2).alias("price_each"),
        F.round(F.col("od.quantityOrdered") * F.col("od.priceEach"), 2).alias("sales_amount"),
    )
)

require_non_empty(fact_orders, "fact_orders")
require_non_empty(dim_customers, "dim_customers")
require_non_empty(dim_products, "dim_products")
require_non_empty(dim_dates, "dim_dates")
require_non_empty(dim_countries, "dim_countries")

ensure_no_orphans(fact_orders, dim_customers, dim_products, dim_dates, dim_countries)
ensure_sales_amount(fact_orders)

write_parquet(fact_orders, args["output_bucket"], args["output_prefix"], "fact_orders")
write_parquet(dim_customers, args["output_bucket"], args["output_prefix"], "dim_customers")
write_parquet(dim_products, args["output_bucket"], args["output_prefix"], "dim_products")
write_parquet(dim_dates, args["output_bucket"], args["output_prefix"], "dim_dates")
write_parquet(dim_countries, args["output_bucket"], args["output_prefix"], "dim_countries")

job.commit()
