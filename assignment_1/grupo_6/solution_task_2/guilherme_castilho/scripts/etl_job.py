import sys
from awsglue.transforms import *
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from awsglue.context import GlueContext
from awsglue.job import Job
from pyspark.sql.functions import col, concat_ws, date_format, year, quarter, month, dayofmonth, monotonically_increasing_id

# Inicialização
args = getResolvedOptions(sys.argv, ['JOB_NAME', 'S3_TARGET_PATH', 'CONNECTION_NAME', 'DB_NAME'])
sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)
job.init(args['JOB_NAME'], args)

s3_target = args['S3_TARGET_PATH']
conn_name = args['CONNECTION_NAME']
db_name = args['DB_NAME']

# 1. Extração
def extract_table(table_name):
    return glueContext.create_dynamic_frame.from_options(
        connection_type="mysql",
        connection_options={
            "useConnectionProperties": "true",
            "connectionName": conn_name,
            "dbtable": table_name
        }
    ).toDF()

df_customers = extract_table("customers")
df_products = extract_table("products")
df_orders = extract_table("orders")
df_orderdetails = extract_table("orderdetails")

# 2. Transformação (Esquema Estrela)[cite: 2]

# dim_customers[cite: 2]
dim_customers = df_customers.select(
    col("customerNumber").alias("customer_id"),
    col("customerName").alias("customer_name"),
    concat_ws(" ", col("contactFirstName"), col("contactLastName")).alias("contact_name"),
    col("city"),
    col("country")
)

# dim_products[cite: 2]
dim_products = df_products.select(
    col("productCode").alias("product_id"),
    col("productName").alias("product_name"),
    col("productLine").alias("product_line"),
    col("productVendor").alias("product_vendor")
)

# dim_countries[cite: 2]
dim_countries = df_customers.select("country").distinct().withColumn("country_key", monotonically_increasing_id())
# (Nota: 'territory' não existe na tabela customers do classicmodels original, mantido o country como granularidade)
dim_countries = dim_countries.select(
    col("country_key"),
    col("country"),
    col("country").alias("territory") 
)

# dim_dates[cite: 2]
dim_dates = df_orders.select("orderDate").distinct()
dim_dates = dim_dates.select(
    date_format(col("orderDate"), "yyyyMMdd").alias("date_key"),
    col("orderDate").alias("full_date"),
    year(col("orderDate")).alias("year"),
    quarter(col("orderDate")).alias("quarter"),
    month(col("orderDate")).alias("month"),
    dayofmonth(col("orderDate")).alias("day")
)

# fact_orders[cite: 2]
# Join orders e orderdetails
fact_orders = df_orders.join(df_orderdetails, "orderNumber")
# Join com customers para pegar o country (necessário para a chave do country)
fact_orders = fact_orders.join(df_customers, "customerNumber")
# Join com dim_countries para pegar a country_key
fact_orders = fact_orders.join(dim_countries, "country")

fact_orders = fact_orders.select(
    col("orderNumber").alias("order_id"),
    col("customerNumber").alias("customer_id"),
    col("productCode").alias("product_id"),
    date_format(col("orderDate"), "yyyyMMdd").alias("order_date_key"),
    col("country_key"),
    col("quantityOrdered").cast("int").alias("quantity_ordered"),
    col("priceEach").cast("double").alias("price_each"),
    (col("quantityOrdered") * col("priceEach")).cast("double").alias("sales_amount") # Regra de negócio[cite: 2]
)

# 3. Load (Salvar em S3 no formato Parquet)[cite: 2]
def load_to_s3(df, table_name):
    df.write.mode("overwrite").parquet(f"{s3_target}{table_name}/")

load_to_s3(dim_customers, "dim_customers")
load_to_s3(dim_products, "dim_products")
load_to_s3(dim_countries, "dim_countries")
load_to_s3(dim_dates, "dim_dates")
load_to_s3(fact_orders, "fact_orders")

job.commit()