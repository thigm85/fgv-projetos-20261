import sys
from datetime import datetime, timezone

from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.transforms import *
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from pyspark.sql import functions as F
from pyspark.sql.types import IntegerType

args = getResolvedOptions(
    sys.argv,
    [
        "JOB_NAME",
        "jdbc_url",          
        "db_user",
        "db_password",     
        "s3_output_path",  
        "pipeline_name",   
    ],
)

sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)
job.init(args["JOB_NAME"], args)

JDBC_URL = args["jdbc_url"]
DB_USER = args["db_user"]
DB_PASSWORD = args["db_password"]
S3_OUTPUT = args["s3_output_path"].rstrip("/")
PIPELINE_NAME = args["pipeline_name"]

JDBC_OPTIONS = {
    "url": JDBC_URL,
    "user": DB_USER,
    "password": DB_PASSWORD,
    "driver": "com.mysql.cj.jdbc.Driver",
}

def read_table(table: str):
    return (
        spark.read.format("jdbc")
        .options(**JDBC_OPTIONS, dbtable=table)
        .load()
    )

def read_query(query: str, tmp_alias: str):
    return (
        spark.read.format("jdbc")
        .options(**JDBC_OPTIONS, dbtable=f"({query}) AS {tmp_alias}")
        .load()
    )

def jdbc_execute(sql: str):
    """Executa DDL/DML no RDS via JDBC (single-partition read trick)."""
    spark.read.format("jdbc").options(
        **JDBC_OPTIONS,
        dbtable=f"({sql}; SELECT 1) AS noop",
    ).load()

wm_df = read_query(
    f"SELECT last_processed_order_date, last_run_at, last_run_status "
    f"FROM etl_watermark WHERE pipeline_name = '{PIPELINE_NAME}'",
    "wm",
)

NEVER_RUN_SENTINEL = "1900-01-01"

if wm_df.count() == 0:
    # Primeira execução — insere registro inicial
    last_date_str = NEVER_RUN_SENTINEL
    jdbc_execute(
        f"INSERT INTO etl_watermark (pipeline_name, last_processed_order_date, last_run_at, last_run_status) "
        f"VALUES ('{PIPELINE_NAME}', '{NEVER_RUN_SENTINEL}', NOW(), 'RUNNING')"
    )
else:
    row = wm_df.collect()[0]
    raw = str(row["last_processed_order_date"])
    last_date_str = NEVER_RUN_SENTINEL if raw in ("NEVER_RUN", "None", "") else raw
    # Marca run como RUNNING
    jdbc_execute(
        f"UPDATE etl_watermark SET last_run_at = NOW(), last_run_status = 'RUNNING' "
        f"WHERE pipeline_name = '{PIPELINE_NAME}'"
    )

print(f"[ETL] Watermark: {last_date_str}")

orders_delta = read_query(
    f"SELECT * FROM orders WHERE orderDate > '{last_date_str}'",
    "orders_delta",
)
delta_count = orders_delta.count()
print(f"[ETL] Pedidos no delta: {delta_count}")

if delta_count == 0:
    print("[ETL] Sem novos pedidos. Atualizando status e encerrando.")
    jdbc_execute(
        f"UPDATE etl_watermark SET last_run_status = 'SUCCEEDED' "
        f"WHERE pipeline_name = '{PIPELINE_NAME}'"
    )
    job.commit()
    sys.exit(0)

order_details = read_table("orderdetails")
customers     = read_table("customers")
products      = read_table("products")
product_lines = read_table("productlines")
offices       = read_table("offices")
employees     = read_table("employees")

dim_customers = (
    customers.select(
        F.col("customerNumber").alias("customer_id"),
        F.col("customerName").alias("customer_name"),
        F.col("city"),
        F.col("country"),
        F.col("creditLimit").alias("credit_limit"),
    )
)

dim_products = (
    products.join(product_lines, "productLine", "left")
    .select(
        F.col("productCode").alias("product_id"),
        F.col("productName").alias("product_name"),
        F.col("productLine").alias("product_line"),
        F.col("productScale").alias("product_scale"),
        F.col("buyPrice").alias("buy_price"),
        F.col("MSRP").alias("msrp"),
    )
)

dim_offices = (
    offices.select(
        F.col("officeCode").alias("office_id"),
        F.col("city").alias("office_city"),
        F.col("country").alias("office_country"),
        F.col("territory"),
    )
)

orders_with_dates = orders_delta.withColumn("orderDate", F.col("orderDate").cast("date"))
dim_dates = (
    orders_with_dates.select(
        F.col("orderDate").alias("date_id"),
        F.year("orderDate").alias("year"),
        F.month("orderDate").alias("month"),
        F.dayofmonth("orderDate").alias("day"),
        F.quarter("orderDate").alias("quarter"),
        F.dayofweek("orderDate").alias("day_of_week"),
    ).distinct()
)

fact_orders = (
    orders_delta.join(order_details, "orderNumber", "inner")
    .join(customers, "customerNumber", "left")
    .join(products, "productCode", "left")
    .join(
        employees.select("employeeNumber", "officeCode"),
        customers["salesRepEmployeeNumber"] == employees["employeeNumber"],
        "left",
    )
    .select(
        F.col("orderNumber").alias("order_id"),
        F.col("productCode").alias("product_id"),
        F.col("customerNumber").alias("customer_id"),
        F.col("officeCode").alias("office_id"),
        F.col("orderDate").cast("date").alias("order_date"),
        F.col("status").alias("order_status"),
        F.col("quantityOrdered").cast(IntegerType()).alias("quantity_ordered"),
        F.col("priceEach").alias("price_each"),
        (F.col("quantityOrdered") * F.col("priceEach")).alias("sales_amount"),
        # Colunas de partição
        F.year(F.col("orderDate")).cast(IntegerType()).alias("order_year"),
        F.month(F.col("orderDate")).cast(IntegerType()).alias("order_month"),
    )
)

dim_map = {
    "dim_customers": dim_customers,
    "dim_products":  dim_products,
    "dim_offices":   dim_offices,
    "dim_dates":     dim_dates,
}

for name, df in dim_map.items():
    path = f"{S3_OUTPUT}/{name}/"
    print(f"[ETL] Gravando {name} em {path}")
    df.write.mode("overwrite").parquet(path)

spark.conf.set("spark.sql.sources.partitionOverwriteMode", "dynamic")

fact_path = f"{S3_OUTPUT}/fact_orders/"
print(f"[ETL] Gravando fact_orders incremental em {fact_path}")
(
    fact_orders
    .write
    .mode("overwrite")
    .partitionBy("order_year", "order_month")
    .parquet(fact_path)
)

try:
    spark.sql(f"MSCK REPAIR TABLE fact_orders")
    print("[ETL] MSCK REPAIR TABLE fact_orders executado.")
except Exception as e:
    print(f"[ETL] MSCK skipped (tabela pode não existir no catálogo ainda): {e}")

max_date_row = orders_delta.agg(F.max("orderDate").alias("max_date")).collect()[0]
max_date = str(max_date_row["max_date"])
now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

jdbc_execute(
    f"UPDATE etl_watermark "
    f"SET last_processed_order_date = '{max_date}', "
    f"    last_run_at = '{now_utc}', "
    f"    last_run_status = 'SUCCEEDED' "
    f"WHERE pipeline_name = '{PIPELINE_NAME}'"
)

print(f"[ETL] Watermark atualizado para {max_date}. Job concluído com sucesso.")
job.commit()
