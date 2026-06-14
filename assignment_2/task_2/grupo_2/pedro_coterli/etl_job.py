import sys
import pymysql
from datetime import datetime, timezone
from awsglue.transforms import *
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from awsglue.context import GlueContext
from awsglue.job import Job
from pyspark.sql.functions import col, concat_ws, year, quarter, month, dayofmonth, date_format, md5, max as spark_max

# Inicialização do Glue
args = getResolvedOptions(sys.argv, ["JOB_NAME", "S3_TARGET_PATH", "DB_HOST", "DB_USER", "DB_PASS", "DB_NAME"])
sc = SparkContext()
glue_context = GlueContext(sc)
spark = glue_context.spark_session

job = Job(glue_context)
job.init(args["JOB_NAME"], args)

S3_OUTPUT = args["S3_TARGET_PATH"]
GLUE_CONNECTION_NAME = "rds_mysql_connection"

def read_mysql_table(table_name):
    return glue_context.create_dynamic_frame.from_options(
        connection_type = "mysql",
        connection_options = {
            "useConnectionProperties": "true",
            "dbtable": table_name,
            "connectionName": GLUE_CONNECTION_NAME,
        }
    ).toDF()

try:
    # Leitura do watermark
    df_watermark = read_mysql_table("etl_watermark")
    watermark_row = df_watermark.filter(col("pipeline_name") == "classicmodels_sales").collect()

    if watermark_row and watermark_row[0]["last_processed_order_date"]:
        last_processed_date = watermark_row[0]["last_processed_order_date"]
    else:
        last_processed_date = '1900-01-01'

    print(f"Iniciando extração incremental a partir de: {last_processed_date}")

    # Extração com filtro incremental
    df_orders = read_mysql_table("orders").filter(col("orderDate") > last_processed_date)

    if df_orders.count() == 0:
        print("Nenhum pedido novo encontrado. Job finalizado.")
        job.commit()
        sys.exit(0)

    # Extração e transformação das dimensões
    df_customers = read_mysql_table("customers")
    df_products = read_mysql_table("products")
    df_orderdetails = read_mysql_table("orderdetails")

    dim_customers = df_customers.select(
        col("customerNumber").alias("customer_id"),
        col("customerName").alias("customer_name"),
        concat_ws(" ", col("contactFirstName"), col("contactLastName")).alias("contact_name"),
        col("city"),
        col("country")
    ).distinct()

    dim_products = df_products.select(
        col("productCode").alias("product_id"),
        col("productName").alias("product_name"),
        col("productLine").alias("product_line"),
        col("productVendor").alias("product_vendor")
    ).distinct()

    dim_dates = df_orders.select(col("orderDate")).distinct() \
        .select(
            date_format(col("orderDate"), "yyyyMMdd").cast("int").alias("date_key"),
            col("orderDate").alias("full_date"),
            year(col("orderDate")).alias("year"),
            quarter(col("orderDate")).alias("quarter"),
            month(col("orderDate")).alias("month"),
            dayofmonth(col("orderDate")).alias("day"),
        )

    dim_countries = df_customers.select(col("country")).distinct() \
        .withColumn("country_key", md5(col("country"))) \
        .withColumn("territory", col("country"))

    # Transformação da tabela fato
    fact_orders = df_orders.join(df_orderdetails, "orderNumber", "inner") \
        .join(df_customers, "customerNumber", "inner") \
        .withColumn("order_date_key", date_format(col("orderDate"), "yyyyMMdd").cast("int")) \
        .withColumn("country_key", md5(df_customers["country"])) \
        .withColumn("sales_amount", col("quantityOrdered") * col("priceEach")) \
        .withColumn("order_year", year(col("orderDate"))) \
        .withColumn("order_month", month(col("orderDate"))) \
        .select(
            col("orderNumber").alias("order_id"),
            col("customerNumber").alias("customer_id"),
            col("productCode").alias("product_id"),
            col("order_date_key"),
            col("country_key"),
            col("quantityOrdered").alias("quantity_ordered"),
            col("priceEach").alias("price_each"),
            col("sales_amount"),
            col("order_year"),
            col("order_month")
        )

    # Carga no S3
    def write_dim_to_s3(df, folder_name):
        path = f"{S3_OUTPUT}/{folder_name}/"
        df.write.mode("overwrite").parquet(path)

    write_dim_to_s3(dim_customers, "dim_customers")
    write_dim_to_s3(dim_products, "dim_products")
    write_dim_to_s3(dim_dates, "dim_dates")
    write_dim_to_s3(dim_countries, "dim_countries")

    fact_path = f"{S3_OUTPUT}/fact_orders/"
    fact_orders.write.mode("append").partitionBy("order_year", "order_month").parquet(fact_path)
    print(f"Fato salva particionada no S3 em: {fact_path}")

    # Atualização do watermark em caso de sucesso
    max_date_row = df_orders.select(spark_max(col("orderDate")).alias("max_date")).collect()
    new_watermark = max_date_row[0]["max_date"]

    if new_watermark:
        conn = pymysql.connect(
            host=args["DB_HOST"], user=args["DB_USER"], password=args["DB_PASS"], database=args["DB_NAME"]
        )
        with conn.cursor() as cursor:
            update_query = """
                UPDATE etl_watermark 
                SET last_processed_order_date = %s, last_run_at = %s, last_run_status = 'SUCCEEDED'
                WHERE pipeline_name = 'classicmodels_sales';
            """
            cursor.execute(update_query, (new_watermark, datetime.now(timezone.utc)))
        conn.commit()
        conn.close()
        print(f"Watermark atualizado com sucesso para: {new_watermark}")

    job.commit()

except Exception as e:
    # Atualização do watermark em caso de falha
    print(f"Erro crítico no Job: {e}")
    try:
        conn = pymysql.connect(
            host=args["DB_HOST"], user=args["DB_USER"], password=args["DB_PASS"], database=args["DB_NAME"]
        )
        with conn.cursor() as cursor:
            update_query = """
                UPDATE etl_watermark 
                SET last_run_status = 'FAILED'
                WHERE pipeline_name = 'classicmodels_sales';
            """
            cursor.execute(update_query)
        conn.commit()
        conn.close()
        print("Status do watermark atualizado para 'FAILED'.")
    except Exception as db_e:
        print(f"Falha ao atualizar o banco com status de erro: {db_e}")
    raise e