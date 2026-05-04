"""
ETL Job — classicmodels (MySQL → Star Schema → Parquet/S3)

Este script é executado pelo AWS Glue (PySpark 3 / Glue 4.0).
Ele:
  1. Extrai tabelas do MySQL RDS via conexão JDBC do Glue
  2. Transforma os dados em um star schema analítico
  3. Grava as tabelas resultantes como Parquet no S3

Tabelas de saída:
  - fact_orders    (tabela fato)
  - dim_customers  (dimensão clientes)
  - dim_products   (dimensão produtos)
  - dim_dates      (dimensão datas)
  - dim_countries  (dimensão países/localidade)
"""

import sys

from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from pyspark.sql import functions as F
from pyspark.sql.window import Window

# ─── Inicialização ──────────────────────────────────────────────────────────
args = getResolvedOptions(sys.argv, ["JOB_NAME", "OUTPUT_BUCKET", "CONNECTION_NAME"])

sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)
job.init(args["JOB_NAME"], args)

OUTPUT_PATH = f"s3://{args['OUTPUT_BUCKET']}"
CONNECTION_NAME = args["CONNECTION_NAME"]

print(f"[ETL] Iniciando job: {args['JOB_NAME']}")
print(f"[ETL] Output bucket: {args['OUTPUT_BUCKET']}")
print(f"[ETL] Connection: {CONNECTION_NAME}")


# ─── Funções auxiliares ─────────────────────────────────────────────────────
def read_mysql_table(table_name: str):
    """Lê uma tabela do MySQL via conexão JDBC do Glue."""
    print(f"[EXTRACT] Lendo tabela: {table_name}")
    df = glueContext.create_dynamic_frame.from_options(
        connection_type="mysql",
        connection_options={
            "useConnectionProperties": "true",
            "dbtable": table_name,
            "connectionName": CONNECTION_NAME,
        },
    ).toDF()
    count = df.count()
    print(f"[EXTRACT] {table_name}: {count} registros")
    return df


# ═════════════════════════════════════════════════════════════════════════════
# 1. EXTRAÇÃO — Ler tabelas necessárias do MySQL
# ═════════════════════════════════════════════════════════════════════════════
print("[ETL] ═══ FASE 1: EXTRAÇÃO ═══")

df_orders = read_mysql_table("orders")
df_orderdetails = read_mysql_table("orderdetails")
df_customers = read_mysql_table("customers")
df_products = read_mysql_table("products")
df_offices = read_mysql_table("offices")
df_employees = read_mysql_table("employees")

# ═════════════════════════════════════════════════════════════════════════════
# 2. TRANSFORMAÇÃO — Montar Star Schema
# ═════════════════════════════════════════════════════════════════════════════
print("[ETL] ═══ FASE 2: TRANSFORMAÇÃO ═══")

# ─── dim_customers ──────────────────────────────────────────────────────────
print("[TRANSFORM] Criando dim_customers")
dim_customers = df_customers.select(
    F.col("customerNumber").alias("customer_id"),
    F.col("customerName").alias("customer_name"),
    F.concat_ws(" ", F.col("contactFirstName"), F.col("contactLastName")).alias(
        "contact_name"
    ),
    F.col("city"),
    F.col("country"),
)
print(f"[TRANSFORM] dim_customers: {dim_customers.count()} registros")

# ─── dim_products ───────────────────────────────────────────────────────────
print("[TRANSFORM] Criando dim_products")
dim_products = df_products.select(
    F.col("productCode").alias("product_id"),
    F.col("productName").alias("product_name"),
    F.col("productLine").alias("product_line"),
    F.col("productVendor").alias("product_vendor"),
)
print(f"[TRANSFORM] dim_products: {dim_products.count()} registros")

# ─── dim_dates ──────────────────────────────────────────────────────────────
# Gera uma dimensão de datas a partir de todas as datas únicas de pedidos
print("[TRANSFORM] Criando dim_dates")
dim_dates = (
    df_orders.select(F.col("orderDate"))
    .distinct()
    .select(
        F.date_format("orderDate", "yyyyMMdd").cast("int").alias("date_key"),
        F.col("orderDate").alias("full_date"),
        F.year("orderDate").alias("year"),
        F.quarter("orderDate").alias("quarter"),
        F.month("orderDate").alias("month"),
        F.dayofmonth("orderDate").alias("day"),
    )
)
print(f"[TRANSFORM] dim_dates: {dim_dates.count()} registros")

# ─── dim_countries ──────────────────────────────────────────────────────────
# Mapeia country → territory via customers → employees → offices
print("[TRANSFORM] Criando dim_countries")

# Join: customers → employees (salesRepEmployeeNumber → employeeNumber)
# → offices (officeCode → officeCode) para obter o territory
customer_territory = (
    df_customers.alias("c")
    .join(
        df_employees.alias("e"),
        F.col("c.salesRepEmployeeNumber") == F.col("e.employeeNumber"),
        "left",
    )
    .join(
        df_offices.alias("o"),
        F.col("e.officeCode") == F.col("o.officeCode"),
        "left",
    )
    .select(
        F.col("c.country").alias("country"),
        F.col("o.territory").alias("territory"),
    )
    .distinct()
)

# Para países sem sales rep (territory = null), preencher com "Unknown"
# Usar a primeira combinação encontrada por país (um país pode ter múltiplos territories)
window_country = Window.partitionBy("country").orderBy(
    F.when(F.col("territory").isNotNull(), 0).otherwise(1)
)

dim_countries = (
    customer_territory.withColumn("rn", F.row_number().over(window_country))
    .filter(F.col("rn") == 1)
    .drop("rn")
    .withColumn("territory", F.coalesce(F.col("territory"), F.lit("Unknown")))
    .withColumn("country_key", F.row_number().over(Window.orderBy("country")))
    .select("country_key", "country", "territory")
)
print(f"[TRANSFORM] dim_countries: {dim_countries.count()} registros")

# ─── fact_orders ────────────────────────────────────────────────────────────
# Join: orders + orderdetails + customers (para country) + dim_countries (para country_key)
print("[TRANSFORM] Criando fact_orders")

fact_orders = (
    df_orderdetails.alias("od")
    .join(df_orders.alias("o"), F.col("od.orderNumber") == F.col("o.orderNumber"))
    .join(
        df_customers.alias("c"),
        F.col("o.customerNumber") == F.col("c.customerNumber"),
    )
    .join(dim_countries.alias("dc"), F.col("c.country") == F.col("dc.country"))
    .select(
        F.col("o.orderNumber").alias("order_id"),
        F.col("o.customerNumber").alias("customer_id"),
        F.col("od.productCode").alias("product_id"),
        F.date_format("o.orderDate", "yyyyMMdd").cast("int").alias("order_date_key"),
        F.col("dc.country_key"),
        F.col("od.quantityOrdered").alias("quantity_ordered"),
        F.col("od.priceEach").alias("price_each"),
        (F.col("od.quantityOrdered") * F.col("od.priceEach")).alias("sales_amount"),
    )
)
print(f"[TRANSFORM] fact_orders: {fact_orders.count()} registros")


# ═════════════════════════════════════════════════════════════════════════════
# 3. LOAD — Gravar Parquet no S3 (uma pasta por tabela)
# ═════════════════════════════════════════════════════════════════════════════
print("[ETL] ═══ FASE 3: LOAD ═══")


def write_parquet(df, table_name: str):
    """Grava um DataFrame como Parquet no S3."""
    path = f"{OUTPUT_PATH}/{table_name}/"
    print(f"[LOAD] Gravando {table_name} em {path}")
    df.write.mode("overwrite").parquet(path)
    print(f"[LOAD] {table_name} gravado com sucesso")


write_parquet(fact_orders, "fact_orders")
write_parquet(dim_customers, "dim_customers")
write_parquet(dim_products, "dim_products")
write_parquet(dim_dates, "dim_dates")
write_parquet(dim_countries, "dim_countries")

# ─── Finalização ────────────────────────────────────────────────────────────
print("[ETL] ═══ JOB CONCLUÍDO COM SUCESSO ═══")
job.commit()
