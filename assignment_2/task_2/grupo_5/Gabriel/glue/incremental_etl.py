import sys
import boto3
import pymysql
from datetime import datetime, timezone

from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from pyspark.sql import functions as F
from pyspark.sql.types import IntegerType

args = getResolvedOptions(
    sys.argv,
    ["JOB_NAME", "S3_BUCKET", "GLUE_DATABASE", "DB_HOST", "DB_USER", "DB_PASSWORD", "DB_NAME"],
)

sc = SparkContext()
glue_context = GlueContext(sc)
spark = glue_context.spark_session
job = Job(glue_context)
job.init(args["JOB_NAME"], args)

S3_BUCKET = args["S3_BUCKET"]
GLUE_DATABASE = args["GLUE_DATABASE"]
DB_HOST = args["DB_HOST"]
DB_USER = args["DB_USER"]
DB_PASSWORD = args["DB_PASSWORD"]
DB_NAME = args["DB_NAME"]

JDBC_URL = f"jdbc:mysql://{DB_HOST}:3306/{DB_NAME}?useSSL=false&allowPublicKeyRetrieval=true"
JDBC_PROPS = {
    "user": DB_USER,
    "password": DB_PASSWORD,
    "driver": "com.mysql.cj.jdbc.Driver",
}

ANALYTICS_PREFIX = f"s3://{S3_BUCKET}/analytics"


def read_table(table: str) -> "DataFrame":
    return spark.read.jdbc(url=JDBC_URL, table=table, properties=JDBC_PROPS)


def read_watermark() -> str:
    df = spark.read.jdbc(
        url=JDBC_URL,
        table="(SELECT last_processed_order_date FROM etl_watermark WHERE pipeline_name = 'classicmodels_sales') AS wm",
        properties=JDBC_PROPS,
    )
    row = df.first()
    if row is None or row["last_processed_order_date"] is None:
        return "1900-01-01"
    return str(row["last_processed_order_date"])


def update_watermark(max_date: str, status: str):
    conn = pymysql.connect(host=DB_HOST, user=DB_USER, password=DB_PASSWORD, database=DB_NAME)
    try:
        with conn.cursor() as cur:
            if status == "SUCCEEDED":
                cur.execute(
                    """
                    UPDATE etl_watermark
                    SET last_processed_order_date = %s,
                        last_run_at = %s,
                        last_run_status = 'SUCCEEDED'
                    WHERE pipeline_name = 'classicmodels_sales'
                    """,
                    (max_date, datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")),
                )
            else:
                cur.execute(
                    """
                    UPDATE etl_watermark
                    SET last_run_at = %s,
                        last_run_status = 'FAILED'
                    WHERE pipeline_name = 'classicmodels_sales'
                    """,
                    (datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),),
                )
        conn.commit()
    finally:
        conn.close()


def register_partitions(glue_client, database: str, table: str, bucket: str, prefix: str):
    paginator = glue_client.get_paginator("get_partitions")
    existing = set()
    for page in paginator.paginate(DatabaseName=database, TableName=table):
        for p in page["Partitions"]:
            existing.add(tuple(p["Values"]))

    s3 = boto3.client("s3")
    result = s3.list_objects_v2(Bucket=bucket, Prefix=prefix, Delimiter="/")
    year_prefixes = [cp["Prefix"] for cp in result.get("CommonPrefixes", [])]

    new_partitions = []
    for yp in year_prefixes:
        year_val = yp.rstrip("/").split("=")[-1]
        sub = s3.list_objects_v2(Bucket=bucket, Prefix=yp, Delimiter="/")
        for mp in sub.get("CommonPrefixes", []):
            month_val = mp["Prefix"].rstrip("/").split("=")[-1]
            key = (year_val, month_val)
            if key not in existing:
                new_partitions.append(
                    {
                        "Values": [year_val, month_val],
                        "StorageDescriptor": {
                            "Location": f"s3://{bucket}/{mp['Prefix']}",
                            "InputFormat": "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat",
                            "OutputFormat": "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat",
                            "SerdeInfo": {
                                "SerializationLibrary": "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe",
                            },
                        },
                    }
                )

    if new_partitions:
        for i in range(0, len(new_partitions), 25):
            glue_client.batch_create_partition(
                DatabaseName=database,
                TableName=table,
                PartitionInputList=new_partitions[i : i + 25],
            )


try:
    watermark_date = read_watermark()
    print(f"Watermark atual: {watermark_date}")

    orders_delta = spark.read.jdbc(
        url=JDBC_URL,
        table=f"(SELECT * FROM orders WHERE orderDate > '{watermark_date}') AS orders_delta",
        properties=JDBC_PROPS,
    )

    count_delta = orders_delta.count()
    print(f"Pedidos novos encontrados: {count_delta}")

    if count_delta == 0:
        print("Nenhum dado novo. Encerrando sem atualizar watermark.")
        job.commit()
        sys.exit(0)

    orderdetails = read_table("orderdetails")
    customers = read_table("customers")
    products = read_table("products")
    productlines = read_table("productlines")
    offices = read_table("offices")
    employees = read_table("employees")

    # ---------- dim_customers ----------
    dim_customers = customers.select(
        F.col("customerNumber").alias("customer_id"),
        F.col("customerName").alias("customer_name"),
        F.concat_ws(" ", F.col("contactFirstName"), F.col("contactLastName")).alias("contact_name"),
        F.col("city"),
        F.col("country"),
    )

    # ---------- dim_products ----------
    dim_products = (
        products.join(productlines, "productLine", "left")
        .select(
            F.col("productCode").alias("product_id"),
            F.col("productName").alias("product_name"),
            F.col("productLine").alias("product_line"),
            F.col("productVendor").alias("product_vendor"),
        )
    )

    customers_for_countries = customers.select(
        F.col("salesRepEmployeeNumber"),
        F.col("country").alias("customer_country"),
    )
    employees_slim = employees.select("employeeNumber", "officeCode")
    offices_slim = offices.select("officeCode", "territory")

    dim_countries = (
        customers_for_countries
        .join(
            employees_slim.join(offices_slim, "officeCode", "left"),
            customers_for_countries["salesRepEmployeeNumber"] == employees_slim["employeeNumber"],
            "left",
        )
        .select(
            F.col("customer_country").alias("country"),
            F.col("territory"),
        )
        .distinct()
        .withColumn("country_key", F.md5(F.col("country")))
    )

    # ---------- dim_dates (derived from delta orders) ----------
    dim_dates = (
        orders_delta.select(F.col("orderDate").alias("full_date")).distinct()
        .select(
            F.date_format(F.col("full_date"), "yyyyMMdd").alias("date_key"),
            F.col("full_date"),
            F.year(F.col("full_date")).alias("year"),
            F.quarter(F.col("full_date")).alias("quarter"),
            F.month(F.col("full_date")).alias("month"),
            F.dayofmonth(F.col("full_date")).alias("day"),
        )
    )

    # ---------- fact_orders (delta) ----------
    cust_lookup = dim_customers.select(
        F.col("customer_id"),
        F.col("country").alias("cust_country"),
    )
    country_lookup = dim_countries.select("country", "country_key")

    orders_with_details = orders_delta.join(orderdetails, "orderNumber", "inner")

    fact_delta = (
        orders_with_details
        .join(cust_lookup, orders_with_details["customerNumber"] == cust_lookup["customer_id"], "left")
        .join(country_lookup, country_lookup["country"] == cust_lookup["cust_country"], "left")
        .select(
            F.col("orderNumber").alias("order_id"),
            F.col("customerNumber").alias("customer_id"),
            F.col("productCode").alias("product_id"),
            F.date_format(F.col("orderDate"), "yyyyMMdd").alias("order_date_key"),
            F.col("country_key"),
            F.col("quantityOrdered").alias("quantity_ordered"),
            F.col("priceEach").alias("price_each"),
            (F.col("quantityOrdered") * F.col("priceEach")).alias("sales_amount"),
            F.year(F.col("orderDate")).cast(IntegerType()).alias("order_year"),
            F.month(F.col("orderDate")).cast(IntegerType()).alias("order_month"),
        )
    )

    max_order_date = orders_delta.agg(F.max("orderDate")).first()[0]
    max_order_date_str = str(max_order_date)

    # ---------- Write dimensions (full overwrite) ----------
    for table_name, df in [
        ("dim_customers", dim_customers),
        ("dim_products", dim_products),
        ("dim_countries", dim_countries),
        ("dim_dates", dim_dates),
    ]:
        (
            df.write.mode("overwrite")
            .parquet(f"{ANALYTICS_PREFIX}/{table_name}/")
        )
        print(f"Dimensão {table_name} gravada.")

    # ---------- Write fact_orders (merge por partição) ----------
    affected_partitions = (
        fact_delta.select("order_year", "order_month").distinct().collect()
    )

    for row in affected_partitions:
        yr, mo = row["order_year"], row["order_month"]
        partition_path = f"{ANALYTICS_PREFIX}/fact_orders/order_year={yr}/order_month={mo}/"

        existing_data = None
        try:
            existing_data = spark.read.parquet(partition_path)
        except Exception:
            pass

        partition_delta = fact_delta.filter(
            (F.col("order_year") == yr) & (F.col("order_month") == mo)
        )

        if existing_data is not None:
            deduped_existing = existing_data.join(
                partition_delta.select("order_id", "product_id"),
                on=["order_id", "product_id"],
                how="left_anti",
            )
            merged = deduped_existing.unionByName(
                partition_delta.drop("order_year", "order_month")
            )
        else:
            merged = partition_delta.drop("order_year", "order_month")

        (
            merged.write.mode("overwrite")
            .parquet(partition_path)
        )
        print(f"Partição order_year={yr}/order_month={mo} gravada.")

    # ---------- Registra partições no Glue Catalog ----------
    glue_client = boto3.client("glue", region_name=boto3.session.Session().region_name)
    register_partitions(
        glue_client,
        database=GLUE_DATABASE,
        table="fact_orders",
        bucket=S3_BUCKET,
        prefix="analytics/fact_orders/",
    )

    update_watermark(max_order_date_str, "SUCCEEDED")
    print(f"Watermark atualizado para {max_order_date_str}. Job concluído com SUCESSO.")

except Exception as exc:
    print(f"ERRO no job: {exc}")
    try:
        update_watermark("", "FAILED")
    except Exception as wm_err:
        print(f"Erro ao gravar FAILED no watermark: {wm_err}")
    raise

job.commit()
