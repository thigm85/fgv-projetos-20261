import sys
import json
import time
import boto3
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.dynamicframe import DynamicFrame


def log(msg):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[ETL][{ts}] {msg}", flush=True)


log("STAGE 0 — resolving job args")
args = getResolvedOptions(sys.argv, ["JOB_NAME", "SECRET_ARN", "S3_BUCKET", "CATALOG_DATABASE"])
log(f"JOB_NAME={args['JOB_NAME']} S3_BUCKET={args['S3_BUCKET']} CATALOG_DATABASE={args['CATALOG_DATABASE']}")

log("STAGE 1 — init Spark / GlueContext")
sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)
job.init(args["JOB_NAME"], args)
log("Spark + Glue context ready")

# ── credentials ───────────────────────────────────────────────────────────────
log("STAGE 2 — fetch secret")
sm = boto3.client("secretsmanager")
secret = json.loads(sm.get_secret_value(SecretId=args["SECRET_ARN"])["SecretString"])
host     = secret["host"]
port     = secret["port"]
user     = secret["username"]
password = secret["password"]
db = secret["dbname"]
log(f"secret resolved host={host} port={port} db={db} user={user}")

jdbc_url = f"jdbc:mysql://{host}:{port}/{db}"
jdbc_opts = {
    "url": jdbc_url,
    "user": user,
    "password": password,
    "driver": "com.mysql.cj.jdbc.Driver",
}

S3 = f"s3://{args['S3_BUCKET']}/data"
log(f"S3 output prefix = {S3}")


# ── extract ───────────────────────────────────────────────────────────────────
log("STAGE 3 — extract tables from MySQL via JDBC")


def read_table(table):
    t0 = time.time()
    log(f"  reading table `{table}` ...")
    df = spark.read.format("jdbc").options(**jdbc_opts, dbtable=table).load()
    n = df.count()
    log(f"  read `{table}` rows={n} elapsed={time.time()-t0:.1f}s")
    return df


orders       = read_table("orders")
orderdetails = read_table("orderdetails")
customers    = read_table("customers")
products     = read_table("products")
productlines = read_table("productlines")
offices = read_table("offices")
employees = read_table("employees")

log("STAGE 3 done — all source tables loaded")

# ── transform ─────────────────────────────────────────────────────────────────
log("STAGE 4 — transformations")
from pyspark.sql import functions as F

# dim_customers
log("building dim_customers")
dim_customers = customers.join(
    employees.select(
        F.col("employeeNumber"),
        F.col("officeCode"),
    ),
    customers["salesRepEmployeeNumber"] == employees["employeeNumber"],
    "left",
).join(
    offices.select("officeCode", "territory"),
    "officeCode",
    "left",
).select(
    F.col("customerNumber").alias("customer_id"),
    F.col("customerName").alias("customer_name"),
    F.concat_ws(" ", F.col("contactFirstName"), F.col("contactLastName")).alias("contact_name"),
    F.col("city"),
    F.col("country"),
    F.col("territory"),
)

# dim_products
log("building dim_products")
dim_products = products.join(productlines, "productLine", "left").select(
    F.col("productCode").alias("product_id"),
    F.col("productName").alias("product_name"),
    F.col("productLine").alias("product_line"),
    F.col("productVendor").alias("product_vendor"),
)

# dim_countries — one row per country (country is the natural PK).
# Territory comes from the sales rep's office, so a country with customers served
# by reps from multiple offices/territories would otherwise produce duplicate rows.
# Aggregate to first non-null territory per country.
log("building dim_countries")
dim_countries = customers.join(
    employees.select("employeeNumber", "officeCode"),
    customers["salesRepEmployeeNumber"] == employees["employeeNumber"],
    "left",
).join(
    offices.select("officeCode", "territory"),
    "officeCode",
    "left",
).groupBy("country").agg(
    F.first("territory", ignorenulls=True).alias("territory"),
).withColumn(
    "country_key", F.md5(F.col("country"))
)

# dim_dates — derived from order dates
log("building dim_dates")
dim_dates = orders.select(F.col("orderDate").alias("full_date")).distinct().withColumn(
    "date_key",  F.date_format(F.col("full_date"), "yyyyMMdd").cast("int"),
    ).withColumn("year",    F.year("full_date")
    ).withColumn("quarter", F.quarter("full_date")
    ).withColumn("month",   F.month("full_date")
    ).withColumn("day",     F.dayofmonth("full_date")
).select("date_key", "full_date", "year", "quarter", "month", "day")

# fact_orders
log("building fact_orders")
# Use using-column join ("customerNumber") to avoid ambiguous column from orders+customers.
fact_base = (
    orderdetails
    .join(orders, "orderNumber")
    .join(customers.select("customerNumber", "country"), "customerNumber", "left")
    .join(dim_countries.select("country", "country_key"), "country", "left")
)

fact_orders = fact_base.select(
    F.col("orderNumber").alias("order_id"),
    F.col("customerNumber").alias("customer_id"),
    F.col("productCode").alias("product_id"),
    F.date_format(F.col("orderDate"), "yyyyMMdd").cast("int").alias("order_date_key"),
    F.col("country_key"),
    F.col("quantityOrdered").alias("quantity_ordered"),
    F.col("priceEach").alias("price_each"),
    (F.col("quantityOrdered") * F.col("priceEach")).alias("sales_amount"),
)
log("STAGE 4 done — transforms defined (lazy)")


# ── load ──────────────────────────────────────────────────────────────────────
log("STAGE 5 — write parquet to S3 + register Glue Catalog")

CATALOG_DB = args["CATALOG_DATABASE"]


def write_catalog(df, name):
    """Escreve Parquet em S3 e registra/atualiza tabela no Glue Catalog num passo."""
    t0 = time.time()
    log(f"  writing {name} → s3 + catalog ({CATALOG_DB}.{name}) ...")
    dyf = DynamicFrame.fromDF(df, glueContext, name)
    sink = glueContext.getSink(
        path=f"{S3}/{name}/",
        connection_type="s3",
        updateBehavior="UPDATE_IN_DATABASE",
        partitionKeys=[],
        enableUpdateCatalog=True,
        transformation_ctx=f"sink_{name}",
    )
    sink.setCatalogInfo(catalogDatabase=CATALOG_DB, catalogTableName=name)
    sink.setFormat("glueparquet")
    sink.writeFrame(dyf)
    log(f"  wrote {name} elapsed={time.time()-t0:.1f}s")


write_catalog(fact_orders, "fact_orders")
write_catalog(dim_customers, "dim_customers")
write_catalog(dim_products, "dim_products")
write_catalog(dim_dates, "dim_dates")
write_catalog(dim_countries, "dim_countries")
log("STAGE 5 done — Parquet + Catalog atualizados")

log("STAGE 6 — job.commit()")
job.commit()
log("ETL FINISHED OK")
