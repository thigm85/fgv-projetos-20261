import sys

from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from pyspark.sql import functions as F
from pyspark.sql.window import Window


args = getResolvedOptions(
    sys.argv,
    [
        "JOB_NAME",
        "db_host",
        "db_port",
        "db_name",
        "db_user",
        "db_password",
        "output_s3_path",
    ],
)

sc = SparkContext()
glue_context = GlueContext(sc)
spark = glue_context.spark_session
job = Job(glue_context)
job.init(args["JOB_NAME"], args)

jdbc_url = (
    f"jdbc:mysql://{args['db_host']}:{args['db_port']}/{args['db_name']}"
    "?useSSL=false&allowPublicKeyRetrieval=true"
)


def read_table(table_name):
    return (
        spark.read.format("jdbc")
        .option("url", jdbc_url)
        .option("driver", "com.mysql.cj.jdbc.Driver")
        .option("dbtable", table_name)
        .option("user", args["db_user"])
        .option("password", args["db_password"])
        .load()
    )


def write_parquet(df, table_name):
    output_path = f"{args['output_s3_path'].rstrip('/')}/{table_name}/"
    df.write.mode("overwrite").parquet(output_path)


orders_df = read_table("orders")
orderdetails_df = read_table("orderdetails")
customers_df = read_table("customers")
products_df = read_table("products")
productlines_df = read_table("productlines")
offices_df = read_table("offices")

dim_customers = (
    customers_df.select(
        F.col("customerNumber").cast("int").alias("customer_id"),
        F.col("customerName").alias("customer_name"),
        F.concat_ws(" ", F.col("contactFirstName"), F.col("contactLastName")).alias("contact_name"),
        F.col("city").alias("city"),
        F.col("country").alias("country"),
    )
    .dropDuplicates(["customer_id"])
)

dim_products = (
    products_df.alias("p").join(
        productlines_df.alias("pl"),
        F.col("p.productLine") == F.col("pl.productLine"),
        "left",
    )
    .select(
        F.col("p.productCode").alias("product_id"),
        F.col("p.productName").alias("product_name"),
        F.col("p.productLine").alias("product_line"),
        F.col("p.productVendor").alias("product_vendor"),
    )
    .dropDuplicates(["product_id"])
)

dates_dim = (
    orders_df.select(F.to_date(F.col("orderDate")).alias("order_date"))
    .where(F.col("order_date").isNotNull())
    .dropDuplicates(["order_date"])
    .select(
        F.date_format(F.col("order_date"), "yyyyMMdd").cast("int").alias("date_key"),
        F.col("order_date").alias("full_date"),
        F.year(F.col("order_date")).cast("int").alias("year"),
        F.quarter(F.col("order_date")).cast("int").alias("quarter"),
        F.month(F.col("order_date")).cast("int").alias("month"),
        F.dayofmonth(F.col("order_date")).cast("int").alias("day"),
    )
)

country_base = customers_df.select(F.col("country")).dropna().dropDuplicates(["country"])
country_with_territory = country_base.join(offices_df.select("country", "territory"), "country", "left")

dim_countries = (
    country_with_territory.select("country", "territory")
    .dropDuplicates(["country"])
    .withColumn(
        "country_key",
        F.dense_rank().over(Window.orderBy(F.col("country"))).cast("int"),
    )
    .select("country_key", "country", "territory")
)

fact_orders_pre = (
    orderdetails_df.alias("od")
    .join(orders_df.alias("o"), F.col("od.orderNumber") == F.col("o.orderNumber"), "inner")
    .join(customers_df.alias("c"), F.col("o.customerNumber") == F.col("c.customerNumber"), "left")
    .select(
        F.col("o.orderNumber").cast("int").alias("order_id"),
        F.col("c.customerNumber").cast("int").alias("customer_id"),
        F.col("od.productCode").alias("product_id"),
        F.date_format(F.to_date(F.col("o.orderDate")), "yyyyMMdd").cast("int").alias("order_date_key"),
        F.col("c.country").alias("country"),
        F.col("od.quantityOrdered").cast("int").alias("quantity_ordered"),
        F.col("od.priceEach").cast("double").alias("price_each"),
    )
    .withColumn("sales_amount", F.round(F.col("quantity_ordered") * F.col("price_each"), 2))
)

fact_orders = (
    fact_orders_pre.alias("f")
    .join(
        dim_countries.alias("dc"),
        F.col("f.country") == F.col("dc.country"),
        "left",
    )
    .select(
        F.col("f.order_id").alias("order_id"),
        F.col("f.customer_id").alias("customer_id"),
        F.col("f.product_id").alias("product_id"),
        F.col("f.order_date_key").alias("order_date_key"),
        F.col("dc.country_key").cast("int").alias("country_key"),
        F.col("f.quantity_ordered").alias("quantity_ordered"),
        F.col("f.price_each").alias("price_each"),
        F.col("f.sales_amount").alias("sales_amount"),
    )
)

write_parquet(fact_orders, "fact_orders")
write_parquet(dim_customers, "dim_customers")
write_parquet(dim_products, "dim_products")
write_parquet(dates_dim, "dates_dim")
write_parquet(dim_countries, "dim_countries")

job.commit()
