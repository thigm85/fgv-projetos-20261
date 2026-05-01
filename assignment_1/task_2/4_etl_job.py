import sys
from awsglue.transforms import *
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from awsglue.context import GlueContext
from awsglue.job import Job
from pyspark.sql.functions import col, concat_ws, year, quarter, month, dayofmonth, date_format, md5

# Inicialização do Glue
args = getResolvedOptions(sys.argv, ["JOB_NAME", "S3_TARGET_PATH"])
sc = SparkContext()
glue_context = GlueContext(sc)
spark = glue_context.spark_session
job = Job(glue_context)
job.init(args["JOB_NAME"], args)

# Variável de saída
S3_OUTPUT = args["S3_TARGET_PATH"]
GLUE_CONNECTION_NAME = "rds_mysql_connection"

# Função de extração
def read_mysql_table(table_name):
    """
    Lê uma tabela do RDS usando a conexão do Glue e converte para Spark DataFrame.
    """
    dynamic_frame = glue_context.create_dynamic_frame.from_options(
        connection_type = "mysql",
        connection_options = {
            "useConnectionProperties": "true",
            "dbtable": table_name,
            "connectionName": GLUE_CONNECTION_NAME,
        }
    )

    return dynamic_frame.toDF()

# Lendo as tabelas do classicmodels
df_customers = read_mysql_table("customers")
df_products = read_mysql_table("products")
df_orders = read_mysql_table("orders")
df_orderdetails = read_mysql_table("orderdetails")

# TRANSFORMAÇÃO

# DIM_CUSTOMERS
dim_customers = df_customers.select(
    col("customerNumber").alias("customer_id"),
    col("customerName").alias("customer_name"),
    concat_ws(" ", col("contactFirstName"), col("contactLastName")).alias("contact_name"),
    col("city"),
    col("country")
).distinct()

# DIM_PRODUCTS
dim_products = df_products.select(
    col("productCode").alias("product_id"),
    col("productName").alias("product_name"),
    col("productLine").alias("product_line"),
    col("productVendor").alias("product_vendor")
).distinct()

# DIM_DATES
# Extraindo datas únicas da tabela de pedidos
dim_dates = df_orders.select(col("orderDate")).distinct() \
    .select(
        date_format(col("orderDate"), "yyyyMMdd").cast("int").alias("date_key"),
        col("orderDate").alias("full_date"),
        year(col("orderDate")).alias("year"),
        quarter(col("orderDate")).alias("quarter"),
        month(col("orderDate")).alias("month"),
        dayofmonth(col("orderDate")).alias("day"),
    )

# DIM_COUNTRIES
# Gerando chaves únicas para os países a partir dos clientes
dim_countries = df_customers.select(col("country")).distinct() \
    .withColumn("country_key", md5(col("country"))) \
    .withColumn("territory", col("country"))

# FACT_ORDERS
# Juntando orders e orderdetails e calculando as métricas
fact_orders = df_orders.join(df_orderdetails, "orderNumber", "inner") \
    .join(df_customers, "customerNumber", "inner") \
    .withColumn("order_date_key", date_format(col("orderDate"), "yyyyMMdd").cast("int")) \
    .withColumn("country_key", md5(df_customers["country"])) \
    .withColumn("sales_amount", col("quantityOrdered") * col("priceEach")) \
    .select(
        col("orderNumber").alias("order_id"),
        col("customerNumber").alias("customer_id"),
        col("productCode").alias("product_id"),
        col("order_date_key"),
        col("country_key"),
        col("quantityOrdered").alias("quantity_ordered"),
        col("priceEach").alias("price_each"),
        col("sales_amount")
    )

# Carga
def write_to_s3(df, folder_name):
    """
    Escreve o DataFrame no S3 em formato Parquet.
    """
    path = f"{S3_OUTPUT}/{folder_name}/"
    df.write.mode("overwrite").parquet(path)
    print(f"Salvo no S3: {path}")

write_to_s3(dim_customers, "dim_customers")
write_to_s3(dim_products, "dim_products")
write_to_s3(dim_dates, "dim_dates")
write_to_s3(dim_countries, "dim_countries")
write_to_s3(fact_orders, "fact_orders")

job.commit()