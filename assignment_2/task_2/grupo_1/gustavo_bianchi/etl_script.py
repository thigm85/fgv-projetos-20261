import sys
import datetime
import boto3
import pymysql
from pyspark.context import SparkContext
from pyspark.sql.functions import col, concat_ws, date_format, year, quarter, month, dayofmonth, monotonically_increasing_id
from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions

# Configuração do Job
args = getResolvedOptions(sys.argv, ['JOB_NAME', 'TARGET_BUCKET', 'CONNECTION_NAME', 'DB_ENDPOINT', 'DB_PASSWORD'])
sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)
job.init(args['JOB_NAME'], args)

TARGET_PATH = f"s3://{args['TARGET_BUCKET']}/analytics/"
CONN_NAME = args['CONNECTION_NAME']

# Habilitar Dynamic Partition Overwrite para a fact_orders
spark.conf.set("spark.sql.sources.partitionOverwriteMode", "dynamic")

def extract_table(table_name):
    dynamic_frame = glueContext.create_dynamic_frame.from_options(
        connection_type="mysql",
        connection_options={
            "useConnectionProperties": "true",
            "dbtable": table_name,
            "connectionName": CONN_NAME
        }
    )
    return dynamic_frame.toDF()

# ---------------------------------------------------------
# 1. Leitura do Watermark
# ---------------------------------------------------------
try:
    df_watermark = extract_table("etl_watermark")
    watermark_row = df_watermark.filter(col("pipeline_name") == "classicmodels_sales").first()
    
    if watermark_row and watermark_row["last_processed_order_date"]:
        last_processed_order_date = watermark_row["last_processed_order_date"].strftime('%Y-%m-%d')
    else:
        last_processed_order_date = "1900-01-01"
except Exception as e:
    print(f"Aviso: Erro ao ler watermark. Iniciando do zero. Detalhe: {e}")
    last_processed_order_date = "1900-01-01"

print(f"Extraindo a partir da data: {last_processed_order_date}")

# ---------------------------------------------------------
# 2. Extração Filtrada (Incremental)
# ---------------------------------------------------------
df_orders_full = extract_table("orders")
df_orders = df_orders_full.filter(col("orderDate") > last_processed_order_date)

df_orders.cache()
is_empty = df_orders.count() == 0

max_date_row = df_orders.agg({"orderDate": "max"}).first()
if max_date_row and max_date_row[0]:
    max_order_date = max_date_row[0].strftime('%Y-%m-%d')
else:
    max_order_date = last_processed_order_date

df_orderdetails = extract_table("orderdetails")
df_customers = extract_table("customers")
df_products = extract_table("products")

# ---------------------------------------------------------
# 3. Transformação (Mantendo o Star Schema e Add Partitions)
# ---------------------------------------------------------
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
    .withColumn("country_key", monotonically_increasing_id().cast("string")) \
    .withColumn("territory", col("country"))

dim_dates = df_orders.select(col("orderDate").alias("full_date")).distinct() \
    .withColumn("date_key", date_format(col("full_date"), "yyyyMMdd").cast("int")) \
    .withColumn("year", year(col("full_date"))) \
    .withColumn("quarter", quarter(col("full_date"))) \
    .withColumn("month", month(col("full_date"))) \
    .withColumn("day", dayofmonth(col("full_date")))

fact_df = df_orders.join(df_orderdetails, "orderNumber")
fact_df = fact_df.join(df_customers.select("customerNumber", "country"), on="customerNumber", how="left")
fact_df = fact_df.join(dim_countries.select("country", "country_key"), on="country", how="left")

fact_df = fact_df.withColumn("sales_amount", col("quantityOrdered") * col("priceEach"))
fact_df = fact_df.withColumn("order_date_key", date_format(col("orderDate"), "yyyyMMdd").cast("int"))

fact_orders = fact_df.select(
    col("orderNumber").alias("order_id"),
    col("productCode").alias("product_id"),
    col("customerNumber").alias("customer_id"),
    col("order_date_key"),
    col("country_key"),
    col("quantityOrdered").alias("quantity_ordered"),
    col("priceEach").cast("double").alias("price_each"),
    col("sales_amount").cast("double"),
    year(col("orderDate")).alias("order_year"),
    month(col("orderDate")).alias("order_month")
)

# ---------------------------------------------------------
# 4. Carga e Merge
# ---------------------------------------------------------
final_status = "FAILED"
try:
    if not is_empty:
        fact_path = f"{TARGET_PATH}fact_orders/"
        affected_parts = fact_orders.select("order_year", "order_month").distinct().collect()
        
        try:
            df_existing = spark.read.parquet(fact_path)
            conds = [f"(order_year = {row.order_year} AND order_month = {row.order_month})" for row in affected_parts]
            filter_expr = " OR ".join(conds)
            
            df_existing_affected = df_existing.filter(filter_expr)
            df_combined = df_existing_affected.unionByName(fact_orders, allowMissingColumns=True)
            df_final_to_write = df_combined.dropDuplicates(["order_id", "product_id"])
        except Exception as e:
            # Diretório vazio ou tabela não existente
            df_final_to_write = fact_orders
            
        # Overwrite das partições
        df_final_to_write.coalesce(1).write.mode("overwrite").partitionBy("order_year", "order_month").parquet(fact_path)
    
    # Sobrescrever dimensões (Opção A)
    dim_customers.coalesce(1).write.mode("overwrite").parquet(f"{TARGET_PATH}dim_customers/")
    dim_products.coalesce(1).write.mode("overwrite").parquet(f"{TARGET_PATH}dim_products/")
    dim_countries.coalesce(1).write.mode("overwrite").parquet(f"{TARGET_PATH}dim_countries/")
    
    if not is_empty:
        dim_dates.coalesce(1).write.mode("append").parquet(f"{TARGET_PATH}dim_dates/")
        
    final_status = "SUCCEEDED"
except Exception as e:
    print(f"Falha na carga: {e}")
    max_order_date = last_processed_order_date

# ---------------------------------------------------------
# 5. Atualizar Watermark no MySQL
# ---------------------------------------------------------
try:
    db_endpoint = args['DB_ENDPOINT']
    db_password = args['DB_PASSWORD']
    
    host_port = db_endpoint.split(":")[0]
    
    conn = pymysql.connect(
        host=host_port,
        user='admin',
        password=db_password,
        database='classicmodels',
        cursorclass=pymysql.cursors.DictCursor
    )
    
    with conn.cursor() as cursor:
        update_query = """
        UPDATE etl_watermark 
        SET last_processed_order_date = %s,
            last_run_at = UTC_TIMESTAMP(),
            last_run_status = %s
        WHERE pipeline_name = %s
        """
        cursor.execute(update_query, (max_order_date, final_status, "classicmodels_sales"))
    conn.commit()
    conn.close()
    print(f"Watermark atualizado! Data: {max_order_date} | Status: {final_status}")

except Exception as e:
    print(f"Falha ao atualizar o watermark no banco de dados: {e}")

if final_status == "FAILED":
    raise Exception("Job finalizado com status FAILED.")

job.commit()