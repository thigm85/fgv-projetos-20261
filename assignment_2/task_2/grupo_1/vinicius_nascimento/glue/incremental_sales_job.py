import sys
import boto3
import pymysql
from datetime import datetime, timezone
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from awsglue.context import GlueContext
from awsglue.job import Job
from pyspark.sql import functions as F
from pyspark.sql.window import Window

# Arguments expected in Glue Job:
# --JOB_NAME
# --jdbc_url jdbc:mysql://<host>:3306/classicmodels
# --jdbc_user <user>
# --jdbc_password <password>
# --s3_analytics_path s3://<bucket>/analytics
# --glue_database <catalog database>
# --pipeline_name classicmodels_sales
# Optional:
# --jdbc_driver com.mysql.cj.jdbc.Driver

args = getResolvedOptions(
    sys.argv,
    [
        "JOB_NAME",
        "jdbc_url",
        "jdbc_user",
        "jdbc_password",
        "s3_analytics_path",
        "glue_database",
        "pipeline_name",
    ],
)

JDBC_URL = args["jdbc_url"]
JDBC_USER = args["jdbc_user"]
JDBC_PASSWORD = args["jdbc_password"]
JDBC_DRIVER = "com.mysql.cj.jdbc.Driver"
S3_ANALYTICS_PATH = args["s3_analytics_path"].rstrip("/")
GLUE_DATABASE = args["glue_database"]
PIPELINE_NAME = args["pipeline_name"]

sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)
job.init(args["JOB_NAME"], args)

spark.conf.set("spark.sql.sources.partitionOverwriteMode", "dynamic")


def mysql_connection_parts(jdbc_url: str):
    # jdbc:mysql://host:3306/classicmodels?x=y
    clean = jdbc_url.replace("jdbc:mysql://", "")
    host_port_db = clean.split("?", 1)[0]
    host_port, database = host_port_db.split("/", 1)
    if ":" in host_port:
        host, port = host_port.split(":", 1)
        port = int(port)
    else:
        host, port = host_port, 3306
    return host, port, database


def read_jdbc_table(table_or_query: str):
    if table_or_query.strip().startswith("("):
        dbtable = table_or_query
    else:
        dbtable = table_or_query
    return (
        spark.read.format("jdbc")
        .option("url", JDBC_URL)
        .option("user", JDBC_USER)
        .option("password", JDBC_PASSWORD)
        .option("driver", JDBC_DRIVER)
        .option("dbtable", dbtable)
        .load()
    )


def update_watermark(status: str, new_date=None):
    host, port, database = mysql_connection_parts(JDBC_URL)
    conn = pymysql.connect(
        host=host,
        port=port,
        user=JDBC_USER,
        password=JDBC_PASSWORD,
        database=database,
        autocommit=False,
    )
    try:
        with conn.cursor() as cur:
            if status == "SUCCEEDED" and new_date is not None:
                cur.execute(
                    """
                    UPDATE etl_watermark
                    SET last_processed_order_date = %s,
                        last_run_at = UTC_TIMESTAMP(),
                        last_run_status = 'SUCCEEDED'
                    WHERE pipeline_name = %s
                    """,
                    (new_date, PIPELINE_NAME),
                )
            else:
                cur.execute(
                    """
                    UPDATE etl_watermark
                    SET last_run_at = UTC_TIMESTAMP(),
                        last_run_status = 'FAILED'
                    WHERE pipeline_name = %s
                    """,
                    (PIPELINE_NAME,),
                )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


try:
    watermark_df = read_jdbc_table(
        f"(SELECT pipeline_name, last_processed_order_date, last_run_status FROM etl_watermark WHERE pipeline_name = '{PIPELINE_NAME}') wm"
    )

    watermark_rows = watermark_df.collect()
    if not watermark_rows:
        raise RuntimeError(f"Watermark not found for pipeline_name={PIPELINE_NAME}")

    last_processed_order_date = watermark_rows[0]["last_processed_order_date"]
    if last_processed_order_date is None:
        raise RuntimeError("last_processed_order_date is NULL. Run Task 1 init_watermark first.")

    print(f"Watermark atual: {last_processed_order_date}")

    orders_delta = read_jdbc_table(
        f"(SELECT * FROM orders WHERE orderDate > '{last_processed_order_date}') orders_delta"
    )

    if orders_delta.rdd.isEmpty():
        print("Nenhum pedido novo encontrado. Atualizando somente status SUCCEEDED sem avançar data.")
        update_watermark("SUCCEEDED", last_processed_order_date)
        job.commit()
        sys.exit(0)

    orderdetails = read_jdbc_table("orderdetails")
    customers = read_jdbc_table("customers")
    products = read_jdbc_table("products")
    productlines = read_jdbc_table("productlines")
    offices = read_jdbc_table("offices")
    employees = read_jdbc_table("employees")

    # -------------------------
    # Dimensões - opção mínima: overwrite completo
    # -------------------------
    dim_customers = (
        customers.alias("c")
        .join(employees.alias("e"), F.col("c.salesRepEmployeeNumber") == F.col("e.employeeNumber"), "left")
        .join(offices.alias("o"), F.col("e.officeCode") == F.col("o.officeCode"), "left")
        .select(
            F.col("c.customerNumber").cast("int").alias("customer_id"),
            F.col("c.customerName").alias("customer_name"),
            F.col("c.contactFirstName").alias("contact_first_name"),
            F.col("c.contactLastName").alias("contact_last_name"),
            F.col("c.phone").alias("phone"),
            F.col("c.city").alias("city"),
            F.col("c.state").alias("state"),
            F.col("c.country").alias("country"),
            F.col("c.creditLimit").cast("double").alias("credit_limit"),
            F.col("e.employeeNumber").cast("int").alias("sales_rep_employee_id"),
            F.concat_ws(" ", F.col("e.firstName"), F.col("e.lastName")).alias("sales_rep_name"),
            F.col("o.officeCode").alias("office_id"),
            F.col("o.city").alias("office_city"),
            F.col("o.country").alias("office_country"),
        )
        .dropDuplicates(["customer_id"])
    )

    dim_products = (
        products.alias("p")
        .join(productlines.alias("pl"), F.col("p.productLine") == F.col("pl.productLine"), "left")
        .select(
            F.col("p.productCode").alias("product_id"),
            F.col("p.productName").alias("product_name"),
            F.col("p.productLine").alias("product_line"),
            F.col("p.productScale").alias("product_scale"),
            F.col("p.productVendor").alias("product_vendor"),
            F.col("p.quantityInStock").cast("int").alias("quantity_in_stock"),
            F.col("p.buyPrice").cast("double").alias("buy_price"),
            F.col("p.MSRP").cast("double").alias("msrp"),
            F.col("pl.textDescription").alias("product_line_description"),
        )
        .dropDuplicates(["product_id"])
    )

    all_order_dates = read_jdbc_table("(SELECT DISTINCT orderDate FROM orders) d")
    dim_dates = (
        all_order_dates
        .select(F.to_date("orderDate").alias("date_id"))
        .dropDuplicates(["date_id"])
        .select(
            F.col("date_id"),
            F.year("date_id").cast("int").alias("year"),
            F.month("date_id").cast("int").alias("month"),
            F.dayofmonth("date_id").cast("int").alias("day"),
            F.quarter("date_id").cast("int").alias("quarter"),
        )
    )

    # Salva dimensões em overwrite completo
    dim_customers.write.mode("overwrite").parquet(f"{S3_ANALYTICS_PATH}/dim_customers/")
    dim_products.write.mode("overwrite").parquet(f"{S3_ANALYTICS_PATH}/dim_products/")
    dim_dates.write.mode("overwrite").parquet(f"{S3_ANALYTICS_PATH}/dim_dates/")

    spark.sql(f"CREATE DATABASE IF NOT EXISTS {GLUE_DATABASE}")
    dim_customers.write.mode("overwrite").format("parquet").saveAsTable(f"{GLUE_DATABASE}.dim_customers")
    dim_products.write.mode("overwrite").format("parquet").saveAsTable(f"{GLUE_DATABASE}.dim_products")
    dim_dates.write.mode("overwrite").format("parquet").saveAsTable(f"{GLUE_DATABASE}.dim_dates")

    # -------------------------
    # Fato incremental
    # Grão: order_id + product_id
    # -------------------------
    fact_delta = (
        orders_delta.alias("o")
        .join(orderdetails.alias("od"), F.col("o.orderNumber") == F.col("od.orderNumber"), "inner")
        .select(
            F.col("o.orderNumber").cast("int").alias("order_id"),
            F.col("od.productCode").alias("product_id"),
            F.col("o.customerNumber").cast("int").alias("customer_id"),
            F.to_date("o.orderDate").alias("order_date"),
            F.to_date("o.requiredDate").alias("required_date"),
            F.to_date("o.shippedDate").alias("shipped_date"),
            F.col("o.status").alias("status"),
            F.col("od.quantityOrdered").cast("int").alias("quantity_ordered"),
            F.col("od.priceEach").cast("double").alias("price_each"),
            (F.col("od.quantityOrdered").cast("double") * F.col("od.priceEach").cast("double")).alias("sales_amount"),
            F.col("od.orderLineNumber").cast("int").alias("order_line_number"),
            F.year("o.orderDate").cast("int").alias("order_year"),
            F.month("o.orderDate").cast("int").alias("order_month"),
        )
    )

    new_max_order_date = fact_delta.agg(F.max("order_date").alias("max_date")).collect()[0]["max_date"]
    affected_partitions = fact_delta.select("order_year", "order_month").dropDuplicates()

    fact_path = f"{S3_ANALYTICS_PATH}/fact_orders/"

    try:
        existing_fact = spark.read.parquet(fact_path)
        existing_affected = existing_fact.join(affected_partitions, ["order_year", "order_month"], "inner")
        existing_unaffected = existing_fact.join(affected_partitions, ["order_year", "order_month"], "left_anti")

        delta_keys = fact_delta.select("order_id", "product_id").dropDuplicates()
        cleaned_existing_affected = existing_affected.join(delta_keys, ["order_id", "product_id"], "left_anti")
        fact_to_write = cleaned_existing_affected.unionByName(fact_delta)

        # Mantém partições não afetadas intocadas e sobrescreve só as afetadas
        fact_to_write.write.mode("overwrite").partitionBy("order_year", "order_month").parquet(fact_path)
    except Exception as read_existing_error:
        print(f"Não foi possível ler fato existente; criando primeira carga incremental. Detalhe: {read_existing_error}")
        fact_delta.write.mode("append").partitionBy("order_year", "order_month").parquet(fact_path)

    # Cria/atualiza tabela Athena apontando para o prefixo particionado
    spark.sql(f"DROP TABLE IF EXISTS {GLUE_DATABASE}.fact_orders")
    spark.sql(
        f"""
        CREATE EXTERNAL TABLE {GLUE_DATABASE}.fact_orders (
            order_id int,
            product_id string,
            customer_id int,
            order_date date,
            required_date date,
            shipped_date date,
            status string,
            quantity_ordered int,
            price_each double,
            sales_amount double,
            order_line_number int
        )
        PARTITIONED BY (order_year int, order_month int)
        STORED AS PARQUET
        LOCATION '{fact_path}'
        """
    )
    spark.sql(f"MSCK REPAIR TABLE {GLUE_DATABASE}.fact_orders")

    update_watermark("SUCCEEDED", new_max_order_date)
    print(f"Watermark atualizado para {new_max_order_date}")
    job.commit()

except Exception as e:
    print(f"ERRO NO JOB: {e}")
    try:
        update_watermark("FAILED", None)
    except Exception as wm_error:
        print(f"Falha ao marcar watermark como FAILED: {wm_error}")
    raise
