"""
AWS Glue ETL Job - classicmodels OLTP -> Star Schema (Parquet no S3)

Esquema estrela produzido:
  fact_orders    : fato central com métricas de vendas
  dim_customers  : dimensão de clientes
  dim_products   : dimensão de produtos
  dim_dates      : dimensão de datas
  dim_countries  : dimensão de localização (país + territory)
"""

import sys
import logging
from datetime import datetime

from awsglue.utils import getResolvedOptions
from awsglue.context import GlueContext
from awsglue.job import Job
from pyspark.context import SparkContext
from pyspark.sql import functions as F
from pyspark.sql.window import Window

# --- Logging ---------------------------------------------------------------------

logger = logging.getLogger("glue_etl")
logger.setLevel(logging.INFO)
_handler = logging.StreamHandler(sys.stdout)
_handler.setFormatter(logging.Formatter("[%(levelname)s] %(asctime)s - %(message)s"))
logger.addHandler(_handler)


def log_step(step: int, total: int, desc: str) -> None:
    logger.info("-" * 60)
    logger.info(f"ETAPA {step}/{total}: {desc}")
    logger.info("-" * 60)


# --- Inicialização ----------------------------------------------------------------

REQUIRED_ARGS = [
    "JOB_NAME",
    "S3_OUTPUT_PATH",
    "RDS_HOST",
    "RDS_PORT",
    "DB_NAME",
    "DB_USERNAME",
    "DB_PASSWORD",
]

args = getResolvedOptions(sys.argv, REQUIRED_ARGS)

sc          = SparkContext()
glueContext = GlueContext(sc)
spark       = glueContext.spark_session
job         = Job(glueContext)
job.init(args["JOB_NAME"], args)

S3_OUTPUT = args["S3_OUTPUT_PATH"].rstrip("/")
JDBC_URL  = (
    f"jdbc:mysql://{args['RDS_HOST']}:{args['RDS_PORT']}/{args['DB_NAME']}"
    "?useSSL=false&serverTimezone=UTC&allowPublicKeyRetrieval=true"
)
JDBC_PROPS = {
    "user":      args["DB_USERNAME"],
    "password":  args["DB_PASSWORD"],
    "driver":    "com.mysql.cj.jdbc.Driver",
    "fetchsize": "1000",
}

logger.info("=" * 60)
logger.info(f"  Job: {args['JOB_NAME']}")
logger.info(f"  Banco: {args['DB_NAME']} em {args['RDS_HOST']}")
logger.info(f"  Destino S3: {S3_OUTPUT}")
logger.info(f"  Início: {datetime.utcnow().isoformat()}Z")
logger.info("=" * 60)


# --- Helpers ---------------------------------------------------------------------

def read_table(table: str):
    """Lê tabela do MySQL via JDBC com logging de contagem."""
    logger.info(f"  -> Lendo '{table}'...")
    df = spark.read.jdbc(url=JDBC_URL, table=table, properties=JDBC_PROPS)
    count = df.count()
    logger.info(f"    '{table}' carregada: {count:,} linhas")
    return df


def write_parquet(df, entity: str) -> int:
    """Grava DataFrame como Parquet no S3 e retorna contagem de registros."""
    path = f"{S3_OUTPUT}/{entity}/"
    count = df.count()
    logger.info(f"  -> Gravando '{entity}' ({count:,} registros) em {path}")
    df.write.mode("overwrite").parquet(path)
    logger.info(f"    '{entity}' salvo com sucesso")
    return count


# ================================================================
# ETAPA 1 - EXTRAÇÃO
# ================================================================
log_step(1, 3, "EXTRAÇÃO - Lendo tabelas do MySQL (classicmodels)")

orders_raw       = read_table("orders")
orderdetails_raw = read_table("orderdetails")
customers_raw    = read_table("customers")
products_raw     = read_table("products")
employees_raw    = read_table("employees")
offices_raw      = read_table("offices")


# ================================================================
# ETAPA 2 - TRANSFORMAÇÃO (Star Schema)
# ================================================================
log_step(2, 3, "TRANSFORMAÇÃO - Modelagem em Esquema Estrela")

# -- dim_customers -----------------------------------------------------------------
logger.info("[dim_customers] Construindo dimensão de clientes...")

dim_customers = (
    customers_raw
    .select(
        F.col("customerNumber").cast("int").alias("customer_id"),
        F.col("customerName").alias("customer_name"),
        F.concat_ws(" ",
            F.col("contactFirstName"),
            F.col("contactLastName"),
        ).alias("contact_name"),
        F.col("city"),
        F.col("country"),
    )
    .distinct()
)
logger.info(f"  dim_customers: {dim_customers.count():,} clientes distintos")

# -- dim_products ------------------------------------------------------------------
logger.info("[dim_products] Construindo dimensão de produtos...")

dim_products = (
    products_raw
    .select(
        F.col("productCode").alias("product_id"),
        F.col("productName").alias("product_name"),
        F.col("productLine").alias("product_line"),
        F.col("productVendor").alias("product_vendor"),
    )
    .distinct()
)
logger.info(f"  dim_products: {dim_products.count():,} produtos distintos")

# -- dim_countries -----------------------------------------------------------------
# Territory vem de: customers.salesRepEmployeeNumber -> employees -> offices.territory
logger.info("[dim_countries] Construindo dimensão de países/territórios...")

# Mapeamento empregado -> territory (via office)
emp_territory = (
    employees_raw
    .join(offices_raw, "officeCode", "inner")
    .select(
        F.col("employeeNumber").alias("employee_number"),
        F.col("territory"),
    )
)

# País de cada cliente + territory do seu representante
country_territory_raw = (
    customers_raw
    .select(
        F.col("country"),
        F.col("salesRepEmployeeNumber").alias("employee_number"),
    )
    .join(emp_territory, "employee_number", "left")
    .select("country", "territory")
)

# Agrega: um país pode ter vários reps -> usa o primeiro territory não-nulo
country_territory_agg = (
    country_territory_raw
    .groupBy("country")
    .agg(F.first("territory", ignorenulls=True).alias("territory"))
    .withColumn(
        "territory",
        F.coalesce(F.col("territory"), F.lit("Unknown")),
    )
)

# Chave surrogate: row_number sobre country (ordenado -> determinístico)
window_countries = Window.orderBy("country")
dim_countries = (
    country_territory_agg
    .withColumn("country_key", F.row_number().over(window_countries))
    .select("country_key", "country", "territory")
)
logger.info(f"  dim_countries: {dim_countries.count():,} países distintos")

# -- dim_dates ---------------------------------------------------------------------
logger.info("[dim_dates] Construindo dimensão de datas...")

dim_dates = (
    orders_raw
    .select("orderDate")
    .dropna(subset=["orderDate"])
    .distinct()
    .select(
        # date_key: inteiro YYYYMMDD para joins eficientes (ex: 20030101)
        F.date_format("orderDate", "yyyyMMdd").cast("int").alias("date_key"),
        F.col("orderDate").alias("full_date"),
        F.year("orderDate").alias("year"),
        F.quarter("orderDate").alias("quarter"),
        F.month("orderDate").alias("month"),
        F.dayofmonth("orderDate").alias("day"),
    )
    .orderBy("date_key")
)
logger.info(f"  dim_dates: {dim_dates.count():,} datas distintas")

# -- fact_orders -------------------------------------------------------------------
logger.info("[fact_orders] Construindo tabela fato de pedidos...")

# Prepara tabelas base com colunas renomeadas para evitar ambiguidade nos joins
orders_base = orders_raw.select(
    F.col("orderNumber").alias("order_number"),
    F.col("customerNumber").cast("int").alias("customer_id"),
    F.date_format("orderDate", "yyyyMMdd").cast("int").alias("order_date_key"),
)

details_base = orderdetails_raw.select(
    F.col("orderNumber").alias("order_number"),
    F.col("productCode").alias("product_id"),
    F.col("quantityOrdered").cast("int").alias("quantity_ordered"),
    F.col("priceEach").cast("double").alias("price_each"),
)

cust_country = customers_raw.select(
    F.col("customerNumber").cast("int").alias("customer_id"),
    F.col("country"),
)

fact_orders = (
    orders_base
    # 1 pedido -> N itens
    .join(details_base, "order_number", "inner")
    # cliente -> país
    .join(cust_country, "customer_id", "inner")
    # país -> country_key (dimensão)
    .join(dim_countries.select("country_key", "country"), "country", "left")
    .select(
        F.col("order_number").alias("order_id"),
        F.col("customer_id"),
        F.col("product_id"),
        F.col("order_date_key"),
        F.col("country_key"),
        F.col("quantity_ordered"),
        F.col("price_each"),
        # sales_amount: regra de negócio explícita (não vem do banco)
        (F.col("quantity_ordered") * F.col("price_each")).alias("sales_amount"),
    )
)

fact_count = fact_orders.count()
logger.info(f"  fact_orders: {fact_count:,} registros (linhas de pedido)")

# Validação rápida pré-load: verifica se sales_amount está consistente
inconsistentes = fact_orders.filter(
    F.abs(
        F.col("sales_amount") - (F.col("quantity_ordered") * F.col("price_each"))
    ) > 0.001
).count()

if inconsistentes > 0:
    logger.warning(f"   {inconsistentes} registros com sales_amount inconsistente!")
else:
    logger.info("   sales_amount consistente em todos os registros")


# ================================================================
# ETAPA 3 - LOAD (Parquet -> S3)
# ================================================================
log_step(3, 3, "LOAD - Gravando Parquet no S3")

counts = {}
counts["fact_orders"]   = write_parquet(fact_orders,   "fact_orders")
counts["dim_customers"] = write_parquet(dim_customers, "dim_customers")
counts["dim_products"]  = write_parquet(dim_products,  "dim_products")
counts["dim_dates"]     = write_parquet(dim_dates,     "dim_dates")
counts["dim_countries"] = write_parquet(dim_countries, "dim_countries")

# --- Sumário final ---------------------------------------------------------------
logger.info("=" * 60)
logger.info("  ETL CONCLUÍDO COM SUCESSO")
logger.info(f"  Fim: {datetime.utcnow().isoformat()}Z")
logger.info("-" * 60)
for entity, count in counts.items():
    logger.info(f"    {entity:<20} {count:>8,} registros -> {S3_OUTPUT}/{entity}/")
logger.info("=" * 60)

job.commit()
