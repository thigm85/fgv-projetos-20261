import sys
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from awsglue.context import GlueContext
from awsglue.job import Job
from pyspark.sql import functions as F
from pyspark.sql.window import Window

args = getResolvedOptions(sys.argv, [
    "JOB_NAME",
    "RDS_ENDPOINT",
    "RDS_PORT",
    "RDS_USERNAME",
    "RDS_PASSWORD",
    "RDS_DB_NAME",
    "S3_OUTPUT_PATH",
])

sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)
job.init(args["JOB_NAME"], args)

jdbc_url = (
    f"jdbc:mysql://{args['RDS_ENDPOINT']}:{args['RDS_PORT']}/{args['RDS_DB_NAME']}"
    "?useSSL=false&allowPublicKeyRetrieval=true"
)
jdbc_props = {
    "user": args["RDS_USERNAME"],
    "password": args["RDS_PASSWORD"],
    "driver": "com.mysql.cj.jdbc.Driver",
}


def read_table(name):
    print(f"[Extract] Lendo tabela: {name}")
    return spark.read.jdbc(url=jdbc_url, table=name, properties=jdbc_props)


# --- Extract ---
customers    = read_table("customers")
orders       = read_table("orders")
orderdetails = read_table("orderdetails")
products     = read_table("products")
productlines = read_table("productlines")
offices      = read_table("offices")

# --- Transform ---

print("[Transform] Construindo dim_customers")
dim_customers = customers.select(
    F.col("customerNumber").alias("customer_id"),
    F.col("customerName").alias("customer_name"),
    F.concat_ws(" ", F.col("contactLastName"), F.col("contactFirstName")).alias("contact_name"),
    F.col("city"),
    F.col("country"),
)

print("[Transform] Construindo dim_products")
dim_products = products.join(productlines, "productLine", "left").select(
    F.col("productCode").alias("product_id"),
    F.col("productName").alias("product_name"),
    F.col("productLine").alias("product_line"),
    F.col("productVendor").alias("product_vendor"),
)

print("[Transform] Construindo dim_dates")
dim_dates = (
    orders.select(F.col("orderDate").alias("full_date")).distinct()
    .withColumn("date_key", F.date_format("full_date", "yyyyMMdd").cast("int"))
    .withColumn("year",     F.year("full_date"))
    .withColumn("quarter",  F.quarter("full_date"))
    .withColumn("month",    F.month("full_date"))
    .withColumn("day",      F.dayofmonth("full_date"))
    .select("date_key", "full_date", "year", "quarter", "month", "day")
)

print("[Transform] Construindo dim_countries")
country_territory = offices.select("country", "territory").distinct()
dim_countries = (
    customers.select("country").distinct()
    .join(country_territory, "country", "left")
    .withColumn("country_key", F.row_number().over(Window.orderBy("country")))
    .select("country_key", "country", "territory")
)

print("[Transform] Construindo fact_orders")
orders_enriched = (
    orders
    .join(customers.select("customerNumber", "country"), "customerNumber")
    .join(dim_countries.select("country_key", "country"), "country")
    .join(
        dim_dates.select("date_key", F.col("full_date").alias("orderDate")),
        "orderDate",
    )
)

fact_orders = orderdetails.join(orders_enriched, "orderNumber").select(
    F.col("orderNumber").alias("order_id"),
    F.col("customerNumber").alias("customer_id"),
    F.col("productCode").alias("product_id"),
    F.col("date_key").alias("order_date_key"),
    F.col("country_key"),
    F.col("quantityOrdered").alias("quantity_ordered"),
    F.col("priceEach").alias("price_each"),
    (F.col("quantityOrdered") * F.col("priceEach")).alias("sales_amount"),
)

# --- Load ---

s3_path = args["S3_OUTPUT_PATH"]


def write_parquet(df, table_name):
    path = f"{s3_path}{table_name}/"
    print(f"[Load] Escrevendo {table_name} em {path}")
    df.write.mode("overwrite").parquet(path)


write_parquet(dim_customers, "dim_customers")
write_parquet(dim_products,  "dim_products")
write_parquet(dim_dates,     "dim_dates")
write_parquet(dim_countries, "dim_countries")
write_parquet(fact_orders,   "fact_orders")

job.commit()
print("[Done] ETL concluído com sucesso.")
