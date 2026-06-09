import sys
from awsglue.transforms import *
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from awsglue.context import GlueContext
from awsglue.job import Job
from pyspark.sql import functions as F
from pyspark.sql.window import Window

# Captura argumentos do Glue Job
args = getResolvedOptions(sys.argv, [
    'JOB_NAME', 
    'connection_name', 
    's3_output_path', 
    'db_name',
    'db_host',
    'db_port',
    'db_user',
    'db_password'
])

sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)
job.init(args['JOB_NAME'], args)

db_name = args['db_name']
connection_name = args['connection_name']
output_path = args['s3_output_path']

def read_table(table_name):
    return glueContext.create_dynamic_frame.from_options(
        connection_type="mysql",
        connection_options={
            "useConnectionProperties": "true",
            "dbtable": f"{db_name}.{table_name}",
            "connectionName": connection_name,
        }
    ).toDF()

def update_watermark_in_rds(status, last_date, max_date=None):
    try:
        import datetime
        import socket
        
        db_host = args['db_host']
        db_port = args['db_port']
        db_name = args['db_name']
        user = args['db_user']
        password = args['db_password']
        
        jdbc_url = f"jdbc:mysql://{db_host}:{db_port}/{db_name}"

        # Log DNS resolution details for debugging
        try:
            resolved_ip = socket.gethostbyname(db_host)
            print(f"[DEBUG DNS] Host '{db_host}' resolvido para IP: {resolved_ip}")
        except Exception as dns_e:
            print(f"[DEBUG DNS] Erro ao resolver host: {dns_e}")

        schema = """
            pipeline_name STRING,
            last_processed_order_date DATE,
            last_run_at TIMESTAMP,
            last_run_status STRING
        """
        # Se max_date for fornecido (sucesso e novos dados), usamos ele. Caso contrário, mantemos o date anterior.
        target_date = max_date if max_date is not None else last_date
        
        # Tratar se last_date for string ou tipo incorreto
        if isinstance(target_date, str):
            from datetime import datetime as dt
            try:
                target_date = dt.strptime(target_date, "%Y-%m-%d").date()
            except ValueError:
                pass

        updated_data = [("classicmodels_sales", target_date, datetime.datetime.now(), status)]
        watermark_update_df = spark.createDataFrame(updated_data, schema=schema)
        
        print(f"Atualizando watermark no RDS via Spark JDBC para status {status} e data {target_date}...")
        watermark_update_df.write \
            .format("jdbc") \
            .option("url", jdbc_url) \
            .option("dbtable", f"{db_name}.etl_watermark") \
            .option("user", user) \
            .option("password", password) \
            .option("truncate", "true") \
            .option("connectTimeout", "10000") \
            .option("socketTimeout", "10000") \
            .mode("overwrite") \
            .save()
        print("Watermark atualizado com sucesso no RDS.")
    except Exception as e:
        print(f"Erro ao atualizar o watermark no RDS: {e}")
        raise e

# Inicializar variável para o bloco catch
last_processed_order_date = "2005-05-31"

try:
    # 1. Obter watermark anterior do RDS
    print("Lendo watermark do RDS...")
    watermark_df = read_table("etl_watermark")
    watermark_row = watermark_df.filter(F.col("pipeline_name") == "classicmodels_sales").select("last_processed_order_date").collect()

    if watermark_row and watermark_row[0]["last_processed_order_date"] is not None:
        last_processed_order_date = watermark_row[0]["last_processed_order_date"]
        print(f"Watermark anterior encontrado: {last_processed_order_date}")
    else:
        print(f"Watermark anterior não encontrado, usando data de fallback: {last_processed_order_date}")

    # 2. Extração
    print(f"Extraindo tabelas do banco {db_name}...")
    customers = read_table("customers")
    products = read_table("products")
    productlines = read_table("productlines")
    offices = read_table("offices")
    employees = read_table("employees")
    
    # Extrair todos os pedidos para gerar a dimensão de datas completa
    all_orders = read_table("orders")
    
    # Filtrar pedidos incrementais pela data
    orders = all_orders.filter(F.col("orderDate") > F.lit(last_processed_order_date))
    new_orders_count = orders.count()
    print(f"Quantidade de novos pedidos identificados: {new_orders_count}")

    # Obter os itens dos pedidos incrementais
    all_orderdetails = read_table("orderdetails")
    orderdetails = all_orderdetails.join(orders.select("orderNumber"), "orderNumber")

    # 3. Transformação
    
    # Dim Customers
    dim_customers = customers.select(
        F.col("customerNumber").alias("customer_id"),
        F.col("customerName").alias("customer_name"),
        F.concat(F.col("contactFirstName"), F.lit(" "), F.col("contactLastName")).alias("contact_name"),
        F.col("city"),
        F.col("country")
    ).distinct()

    # Dim Products
    dim_products = products.join(productlines, "productLine").select(
        F.col("productCode").alias("product_id"),
        F.col("productName").alias("product_name"),
        F.col("productLine").alias("product_line"),
        F.col("productVendor").alias("product_vendor")
    ).distinct()

    # Dim Countries 
    countries_raw = customers.select("country").union(offices.select("country")).distinct()
    territories = offices.select("country", "territory").distinct()
    dim_countries_prep = countries_raw.join(territories, "country", "left") \
        .withColumn("territory", F.coalesce(F.col("territory"), F.lit("Unknown")))

    window_country = Window.orderBy("country")
    dim_countries = dim_countries_prep.filter(F.col("country").isNotNull()).withColumn(
        "country_key", F.row_number().over(window_country)
    ).select("country_key", "country", "territory")

    # Dim Dates (Baseada em todos os pedidos históricos + novos para evitar perda de datas)
    dates_raw = all_orders.select(F.col("orderDate").alias("full_date")).distinct()
    dim_dates = dates_raw.withColumn("date_key", F.date_format(F.col("full_date"), "yyyyMMdd").cast("int")) \
        .withColumn("year", F.year(F.col("full_date"))) \
        .withColumn("quarter", F.quarter(F.col("full_date"))) \
        .withColumn("month", F.month(F.col("full_date"))) \
        .withColumn("day", F.dayofmonth(F.col("full_date")))

    if new_orders_count > 0:
        # Fact Orders incremental
        fact_orders = orders.join(orderdetails, "orderNumber") \
            .join(customers, "customerNumber") \
            .join(dim_countries, customers.country == dim_countries.country, "left") \
            .select(
                F.col("orderNumber").alias("order_id"),
                F.col("customerNumber").alias("customer_id"),
                F.col("productCode").alias("product_id"),
                F.date_format(F.col("orderDate"), "yyyyMMdd").cast("int").alias("order_date_key"),
                F.col("country_key"),
                F.col("quantityOrdered").alias("quantity_ordered"),
                F.col("priceEach").alias("price_each"),
                F.col("orderDate")
            )

        fact_orders = fact_orders.withColumn(
            "sales_amount", 
            F.round(F.col("quantity_ordered") * F.col("price_each"), 2)
        ).withColumn(
            "order_year", F.year(F.col("orderDate"))
        ).withColumn(
            "order_month", F.month(F.col("orderDate"))
        ).drop("orderDate")

        max_order_date_row = orders.select(F.max("orderDate")).collect()
        max_order_date = max_order_date_row[0][0] if max_order_date_row and max_order_date_row[0][0] is not None else None
    else:
        # Criar dataframe fato vazio mantendo a estrutura
        fact_orders = spark.createDataFrame([], schema="""
            order_id INT, customer_id INT, product_id STRING, order_date_key INT,
            country_key INT, quantity_ordered INT, price_each DECIMAL(10,2),
            sales_amount DOUBLE, order_year INT, order_month INT
        """)
        max_order_date = None

    # 4. Carga (Load) para S3 em Parquet
    # Overwrite das dimensões completas
    dimensions_to_load = {
        "dim_customers": dim_customers,
        "dim_products": dim_products,
        "dim_dates": dim_dates,
        "dim_countries": dim_countries
    }

    for table_name, df in dimensions_to_load.items():
        target_dir = f"{output_path}/{table_name}"
        print(f"Salvando dimensão {table_name} em {target_dir}...")
        df.write.mode("overwrite").parquet(target_dir)

    # Carga incremental / merge na tabela fato
    fact_target_dir = f"{output_path}/fact_orders"
    print(f"Salvando fact_orders em {fact_target_dir}...")

    if new_orders_count > 0:
        try:
            existing_fact_df = spark.read.parquet(fact_target_dir)
            fact_exists = True
        except Exception:
            fact_exists = False

        if fact_exists:
            print("Encontrada tabela fact_orders no S3. Executando merge de partições...")
            affected_partitions = fact_orders.select("order_year", "order_month").distinct().collect()
            
            if affected_partitions:
                filter_expr = F.lit(False)
                for row in affected_partitions:
                    filter_expr = filter_expr | (
                        (F.col("order_year") == row["order_year"]) & 
                        (F.col("order_month") == row["order_month"])
                    )
                
                # Filtrar apenas os registros antigos das partições afetadas
                existing_affected_df = existing_fact_df.filter(filter_expr)
                
                # Union com o delta incremental e deduplicação no grão (order_id, product_id)
                merged_affected_df = existing_affected_df.unionByName(fact_orders, allowMissingColumns=True)
                final_fact_df = merged_affected_df.dropDuplicates(["order_id", "product_id"])
            else:
                final_fact_df = fact_orders
        else:
            print("Tabela fact_orders ausente no S3. Gravando primeiro lote...")
            final_fact_df = fact_orders

        # Overwrite dinâmico apenas nas partições afetadas
        spark.conf.set("spark.sql.sources.partitionOverwriteMode", "dynamic")
        final_fact_df.write.partitionBy("order_year", "order_month").mode("overwrite").parquet(fact_target_dir)
        print("Tabela fato gravada com sucesso.")
    else:
        print("Nenhum pedido novo para processar na fato.")

    # 5. Atualização do watermark no RDS MySQL
    if new_orders_count > 0:
        update_watermark_in_rds("SUCCEEDED", last_processed_order_date, max_order_date)
    else:
        update_watermark_in_rds("SUCCEEDED", last_processed_order_date)

    job.commit()

except Exception as e:
    print(f"Erro na execução do Job Glue: {e}")
    try:
        update_watermark_in_rds("FAILED", last_processed_order_date)
    except Exception as inner_e:
        print(f"Falha ao registrar status FAILED no RDS: {inner_e}")
    raise e
