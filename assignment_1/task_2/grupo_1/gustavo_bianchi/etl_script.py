import sys
from pyspark.context import SparkContext
from pyspark.sql.functions import col, concat_ws, date_format, year, quarter, month, dayofmonth, monotonically_increasing_id
from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions

# Configuração do Job
args = getResolvedOptions(sys.argv, ['JOB_NAME', 'TARGET_BUCKET', 'CONNECTION_NAME'])
sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)
job.init(args['JOB_NAME'], args)

TARGET_PATH = f"s3://{args['TARGET_BUCKET']}/"
CONN_NAME = args['CONNECTION_NAME']

def extract_table(table_name):
    # Extração otimizada nativa do Glue via Connection
    dynamic_frame = glueContext.create_dynamic_frame.from_options(
        connection_type="mysql",
        connection_options={
            "useConnectionProperties": "true",
            "dbtable": table_name,
            "connectionName": CONN_NAME
        }
    )
    return dynamic_frame.toDF()

# Extração
df_orders = extract_table("orders")
df_orderdetails = extract_table("orderdetails")
df_customers = extract_table("customers")
df_products = extract_table("products")

# Transformação 
dim_customers = df_customers.select(
    col("customerNumber").alias("customer_id"),
    col("customerName").alias("customer_name"),
    concat_ws(" ", col("contactFirstName"), col("contactLastName")).alias("contact_name"),
    col("city"),
    col("country")
)

dim_products = df_products.select(
    col("productCode").alias("product_id"),
    col("productName").alias("product_name"),
    col("productLine").alias("product_line"),
    col("productVendor").alias("product_vendor")
)

dim_countries = df_customers.select("country").distinct() \
    .withColumn("country_key", monotonically_increasing_id()) \
    .withColumn("territory", col("country"))

dim_dates = df_orders.select(col("orderDate").alias("full_date")).distinct() \
    .withColumn("date_key", date_format(col("full_date"), "yyyyMMdd").cast("int")) \
    .withColumn("year", year(col("full_date"))) \
    .withColumn("quarter", quarter(col("full_date"))) \
    .withColumn("month", month(col("full_date"))) \
    .withColumn("day", dayofmonth(col("full_date")))

# Tabela fato
fact_df = df_orders.join(df_orderdetails, "orderNumber")
fact_df = fact_df.join(df_customers.select("customerNumber", "country"), on="customerNumber", how="left")
fact_df = fact_df.join(dim_countries.select("country", "country_key"), on="country", how="left")

# Métricas e Chaves
fact_df = fact_df.withColumn("sales_amount", col("quantityOrdered") * col("priceEach"))
fact_df = fact_df.withColumn("order_date_key", date_format(col("orderDate"), "yyyyMMdd").cast("int"))

fact_orders = fact_df.select(
    col("orderNumber").alias("order_id"),
    col("customerNumber").alias("customer_id"),
    col("productCode").alias("product_id"),
    col("order_date_key"),
    col("country_key"),
    col("quantityOrdered").alias("quantity_ordered"),
    col("priceEach").alias("price_each"),
    col("sales_amount")
)

# Carregamento
def load_to_s3(df, folder_name):
    path = f"{TARGET_PATH}{folder_name}/"
    df.coalesce(1).write.mode("overwrite").parquet(path)

load_to_s3(fact_orders, "fact_orders")
load_to_s3(dim_customers, "dim_customers")
load_to_s3(dim_products, "dim_products")
load_to_s3(dim_dates, "dim_dates")
load_to_s3(dim_countries, "dim_countries")

job.commit()