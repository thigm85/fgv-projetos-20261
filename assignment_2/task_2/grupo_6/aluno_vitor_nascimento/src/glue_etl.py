import sys
from awsglue.transforms import *
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from awsglue.context import GlueContext
from awsglue.job import Job
from pyspark.sql.functions import col, concat, lit, year, quarter, month, dayofmonth
from datetime import datetime

# Resolve Job arguments
args = getResolvedOptions(sys.argv, ['JOB_NAME', 'S3_OUTPUT_PATH', 'RDS_CONNECTION_NAME', 'DB_NAME'])

sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)
job.init(args['JOB_NAME'], args)

s3_output = args['S3_OUTPUT_PATH']
connection_name = args['RDS_CONNECTION_NAME']
db_name = args['DB_NAME']

def read_table(table_name):
    return glueContext.create_dynamic_frame.from_options(
        connection_type="mysql",
        connection_options={
            "useConnectionProperties": "true",
            "dbtable": f"{db_name}.{table_name}",
            "connectionName": connection_name,
        }
    ).toDF()

def update_watermark(last_processed_date, status):
    import boto3
    glue_client = boto3.client("glue", region_name="us-east-1")
    conn_details = glue_client.get_connection(Name=connection_name)["Connection"]["ConnectionProperties"]
    jdbc_url = conn_details["JDBC_CONNECTION_URL"]
    user = conn_details["USERNAME"]
    password = conn_details["PASSWORD"]
    
    now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    driver_class = "com.mysql.cj.jdbc.Driver"
    
    jvm = spark._jvm
    jvm.Class.forName(driver_class)
    conn_props = jvm.java.util.Properties()
    conn_props.setProperty("user", user)
    conn_props.setProperty("password", password)
    
    conn = jvm.java.sql.DriverManager.getConnection(jdbc_url, conn_props)
    try:
        stmt = conn.prepareStatement(
            "INSERT INTO etl_watermark (pipeline_name, last_processed_order_date, last_run_at, last_run_status) "
            "VALUES (?, ?, ?, ?) "
            "ON DUPLICATE KEY UPDATE last_processed_order_date = VALUES(last_processed_order_date), "
            "last_run_at = VALUES(last_run_at), last_run_status = VALUES(last_run_status)"
        )
        stmt.setString(1, "classicmodels_sales")
        if last_processed_date:
            stmt.setString(2, last_processed_date)
        else:
            stmt.setNull(2, jvm.java.sql.Types.DATE)
        stmt.setString(3, now_str)
        stmt.setString(4, status)
        stmt.executeUpdate()
        stmt.close()
    finally:
        conn.close()

try:
    # 1. Obter watermark
    watermark_df = read_table("etl_watermark")
    watermark_row = watermark_df.filter(col("pipeline_name") == "classicmodels_sales").collect()
    
    last_run_status = "NEVER_RUN"
    if watermark_row:
        last_run_status = watermark_row[0]["last_run_status"]
        last_processed_date_val = watermark_row[0]["last_processed_order_date"]
        # Se for um objeto datetime.date, formatar como string
        if hasattr(last_processed_date_val, "strftime"):
            last_processed_order_date = last_processed_date_val.strftime("%Y-%m-%d")
        else:
            last_processed_order_date = str(last_processed_date_val) if last_processed_date_val is not None else "1970-01-01"
    else:
        last_processed_order_date = "1970-01-01"
    
    # Verificar se a tabela fato existe no S3
    fact_output_path = f"{s3_output}/fact_orders"
    s3_exists = False
    try:
        spark.read.parquet(fact_output_path).limit(1).collect()
        s3_exists = True
    except Exception:
        s3_exists = False
        
    # Se for a primeira execucao ou se o S3 estiver vazio, forcamos o carregamento de todo o historico
    if last_run_status == "NEVER_RUN" or not s3_exists:
        print("Primeira execucao incremental ou S3 vazio detectado. Carregando todo o historico.")
        last_processed_order_date_filter = "1970-01-01"
    else:
        print(f"Execucao incremental. Filtrando pedidos a partir de: {last_processed_order_date}")
        last_processed_order_date_filter = last_processed_order_date
    
    # 2. Ler todas as tabelas necessarias (incluindo productlines e offices para atender ao requisito)
    customers = read_table("customers")
    products = read_table("products")
    orders_all = read_table("orders")
    order_details = read_table("orderdetails")
    product_lines = read_table("productlines")
    offices = read_table("offices")
    
    # Filtrar ordens incrementais
    orders_delta = orders_all.filter(col("orderDate") > last_processed_order_date_filter)
    new_orders_count = orders_delta.count()
    print(f"Numero de novas ordens encontradas: {new_orders_count}")
    
    # 3. Processar Fato
    fact_orders_delta = orders_delta.join(order_details, "orderNumber") \
        .join(customers.select("customerNumber", "country"), "customerNumber") \
        .select(
            col("orderNumber").alias("order_id"),
            col("customerNumber").alias("customer_id"),
            col("productCode").alias("product_id"),
            col("orderDate").alias("order_date_key"),
            col("country").alias("country_key"),
            col("quantityOrdered").alias("quantity_ordered"),
            col("priceEach").alias("price_each"),
            (col("quantityOrdered") * col("priceEach")).cast("decimal(10,2)").alias("sales_amount")
        )
    
    # Adicionar colunas de particao
    fact_orders_delta = fact_orders_delta \
        .withColumn("order_year", year(col("order_date_key")).cast("int")) \
        .withColumn("order_month", month(col("order_date_key")).cast("int"))
        
    # Merge incremental da Fato
    fact_output_path = f"{s3_output}/fact_orders"
    temp_output_path = f"{s3_output}/fact_orders_temp"
    try:
        existing_fact = spark.read.parquet(fact_output_path)
        if "order_year" not in existing_fact.columns:
            existing_fact = existing_fact \
                .withColumn("order_year", year(col("order_date_key")).cast("int")) \
                .withColumn("order_month", month(col("order_date_key")).cast("int"))
        
        merged_fact = existing_fact.unionByName(fact_orders_delta, allowMissingColumns=True) \
            .dropDuplicates(["order_id", "product_id"])
        
        # Escrever para pasta temporaria para evitar ler e escrever no mesmo local simultaneamente
        merged_fact.write.mode("overwrite").partitionBy("order_year", "order_month").parquet(temp_output_path)
        
        # Substituir a pasta original usando a API Hadoop FileSystem (JVM)
        path_class = spark._jvm.org.apache.hadoop.fs.Path
        fs = path_class(fact_output_path).getFileSystem(spark._jsc.hadoopConfiguration())
        
        # Deleta a pasta original e renomeia a temporaria
        fs.delete(path_class(fact_output_path), True)
        fs.rename(path_class(temp_output_path), path_class(fact_output_path))
    except Exception as e:
        print(f"Tabela fato nao encontrada no S3 ou erro ao processar merge. Criando nova fato a partir do delta. Detalhe: {e}")
        fact_orders_delta.write.mode("overwrite").partitionBy("order_year", "order_month").parquet(fact_output_path)
    
    # 4. Processar e escrever dimensoes (sobregravacao completa - Opcao A)
    dim_customers = customers.select(
        col("customerNumber").alias("customer_id"),
        col("customerName").alias("customer_name"),
        concat(col("contactFirstName"), lit(" "), col("contactLastName")).alias("contact_name"),
        col("city"),
        col("country")
    )
    
    dim_products = products.select(
        col("productCode").alias("product_id"),
        col("productName").alias("product_name"),
        col("productLine").alias("product_line"),
        col("productVendor").alias("product_vendor")
    )
    
    dim_countries = customers.select("country").distinct() \
        .select(
            col("country").alias("country_key"),
            col("country"),
            lit("Unknown").alias("territory")
        )
        
    dim_dates = orders_all.select(col("orderDate").alias("full_date")).distinct() \
        .select(
            col("full_date").alias("date_key"),
            "full_date",
            year("full_date").alias("year"),
            quarter("full_date").alias("quarter"),
            month("full_date").alias("month"),
            dayofmonth("full_date").alias("day")
        )
        
    def write_parquet(df, table_name):
        df.write.mode("overwrite").parquet(f"{s3_output}/{table_name}/")
        
    write_parquet(dim_customers, "dim_customers")
    write_parquet(dim_products, "dim_products")
    write_parquet(dim_dates, "dim_dates")
    write_parquet(dim_countries, "dim_countries")
    
    # 5. Autorizar/Atualizar watermark com sucesso
    if new_orders_count > 0:
        max_order_date_val = orders_delta.agg({"orderDate": "max"}).collect()[0][0]
        if hasattr(max_order_date_val, "strftime"):
            max_order_date_str = max_order_date_val.strftime("%Y-%m-%d")
        else:
            max_order_date_str = str(max_order_date_val)
    else:
        max_order_date_str = last_processed_order_date
        
    update_watermark(max_order_date_str, "SUCCEEDED")
    print(f"Execucao concluida com sucesso. Watermark atualizado para {max_order_date_str}")
    
except Exception as e:
    print(f"Erro na execucao do pipeline: {e}")
    try:
        if 'last_processed_order_date' in locals():
            update_watermark(last_processed_order_date, "FAILED")
        else:
            update_watermark(None, "FAILED")
    except Exception as watermark_err:
        print(f"Erro ao tentar atualizar status de watermark para FAILED: {watermark_err}")
    raise e

job.commit()
