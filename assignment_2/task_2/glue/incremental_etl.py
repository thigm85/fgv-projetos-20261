import sys
from datetime import datetime, timezone

import boto3
import pymysql
from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from pyspark.sql import functions as F
from pyspark.sql.types import IntegerType


PIPELINE_NAME = "classicmodels_sales"
WATERMARK_FALLBACK = "1900-01-01"
FACT_TABLE = "fact_orders"
FACT_KEYS = ["order_id", "product_id"]
PARTITION_COLUMNS = ["order_year", "order_month"]


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
JDBC_OPTIONS = {
    "user": DB_USER,
    "password": DB_PASSWORD,
    "driver": "com.mysql.cj.jdbc.Driver",
}

ANALYTICS_ROOT = f"s3://{S3_BUCKET}/analytics"


def utc_now_sql() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def read_table(table_name: str):
    return spark.read.jdbc(url=JDBC_URL, table=table_name, properties=JDBC_OPTIONS)


def read_query(query: str, alias: str):
    return spark.read.jdbc(
        url=JDBC_URL,
        table=f"({query}) AS {alias}",
        properties=JDBC_OPTIONS,
    )


def read_watermark() -> str:
    watermark_df = read_query(
        f"""
        SELECT last_processed_order_date
        FROM etl_watermark
        WHERE pipeline_name = '{PIPELINE_NAME}'
        """,
        "watermark",
    )

    row = watermark_df.first()
    if row is None or row["last_processed_order_date"] is None:
        return WATERMARK_FALLBACK

    return str(row["last_processed_order_date"])


def update_watermark(status: str, max_order_date: str | None = None):
    connection = pymysql.connect(host=DB_HOST, user=DB_USER, password=DB_PASSWORD, database=DB_NAME)
    try:
        with connection.cursor() as cursor:
            if status == "SUCCEEDED":
                cursor.execute(
                    """
                    UPDATE etl_watermark
                    SET last_processed_order_date = %s,
                        last_run_at = %s,
                        last_run_status = 'SUCCEEDED'
                    WHERE pipeline_name = %s
                    """,
                    (max_order_date, utc_now_sql(), PIPELINE_NAME),
                )
            else:
                cursor.execute(
                    """
                    UPDATE etl_watermark
                    SET last_run_at = %s,
                        last_run_status = 'FAILED'
                    WHERE pipeline_name = %s
                    """,
                    (utc_now_sql(), PIPELINE_NAME),
                )
        connection.commit()
    finally:
        connection.close()


def read_order_delta(watermark_date: str):
    return read_query(
        f"""
        SELECT *
        FROM orders
        WHERE orderDate > '{watermark_date}'
        """,
        "orders_delta",
    )


def build_dimensions(orders_delta, source_tables: dict):
    customers = source_tables["customers"]
    employees = source_tables["employees"]
    offices = source_tables["offices"]
    products = source_tables["products"]
    productlines = source_tables["productlines"]

    dim_customers = customers.select(
        F.col("customerNumber").alias("customer_id"),
        F.col("customerName").alias("customer_name"),
        F.concat_ws(" ", F.col("contactFirstName"), F.col("contactLastName")).alias("contact_name"),
        F.col("city"),
        F.col("country"),
    )

    dim_products = products.join(productlines, "productLine", "left").select(
        F.col("productCode").alias("product_id"),
        F.col("productName").alias("product_name"),
        F.col("productLine").alias("product_line"),
        F.col("productVendor").alias("product_vendor"),
    )

    sales_rep_offices = employees.select("employeeNumber", "officeCode").join(
        offices.select("officeCode", "territory"),
        "officeCode",
        "left",
    )

    dim_countries = (
        customers.select(
            F.col("salesRepEmployeeNumber"),
            F.col("country").alias("customer_country"),
        )
        .join(
            sales_rep_offices,
            F.col("salesRepEmployeeNumber") == F.col("employeeNumber"),
            "left",
        )
        .select(
            F.col("customer_country").alias("country"),
            F.col("territory"),
        )
        .distinct()
        .withColumn("country_key", F.md5(F.col("country")))
    )

    dim_dates = (
        orders_delta.select(F.col("orderDate").alias("full_date"))
        .distinct()
        .select(
            F.date_format("full_date", "yyyyMMdd").alias("date_key"),
            F.col("full_date"),
            F.year("full_date").alias("year"),
            F.quarter("full_date").alias("quarter"),
            F.month("full_date").alias("month"),
            F.dayofmonth("full_date").alias("day"),
        )
    )

    return {
        "dim_customers": dim_customers,
        "dim_products": dim_products,
        "dim_countries": dim_countries,
        "dim_dates": dim_dates,
    }


def build_fact_delta(orders_delta, orderdetails, dimensions: dict):
    customer_lookup = dimensions["dim_customers"].select(
        F.col("customer_id"),
        F.col("country").alias("customer_country"),
    )
    country_lookup = dimensions["dim_countries"].select("country", "country_key")

    return (
        orders_delta.join(orderdetails, "orderNumber", "inner")
        .join(
            customer_lookup,
            F.col("customerNumber") == F.col("customer_id"),
            "left",
        )
        .join(
            country_lookup,
            F.col("customer_country") == F.col("country"),
            "left",
        )
        .select(
            F.col("orderNumber").alias("order_id"),
            F.col("customerNumber").alias("customer_id"),
            F.col("productCode").alias("product_id"),
            F.date_format("orderDate", "yyyyMMdd").alias("order_date_key"),
            F.col("country_key"),
            F.col("quantityOrdered").alias("quantity_ordered"),
            F.col("priceEach").alias("price_each"),
            (F.col("quantityOrdered") * F.col("priceEach")).alias("sales_amount"),
            F.year("orderDate").cast(IntegerType()).alias("order_year"),
            F.month("orderDate").cast(IntegerType()).alias("order_month"),
        )
    )


def write_dimensions(dimensions: dict):
    for table_name, dataframe in dimensions.items():
        dataframe.write.mode("overwrite").parquet(f"{ANALYTICS_ROOT}/{table_name}/")
        print(f"Dimensao atualizada: {table_name}")


def merge_fact_partitions(fact_delta):
    touched_partitions = fact_delta.select(*PARTITION_COLUMNS).distinct().collect()

    for row in touched_partitions:
        order_year = row["order_year"]
        order_month = row["order_month"]
        partition_delta = fact_delta.filter(
            (F.col("order_year") == order_year) & (F.col("order_month") == order_month)
        )
        partition_path = (
            f"{ANALYTICS_ROOT}/{FACT_TABLE}/"
            f"order_year={order_year}/order_month={order_month}/"
        )

        try:
            current_partition = spark.read.parquet(partition_path)
        except Exception:
            current_partition = None

        delta_without_partition_cols = partition_delta.drop(*PARTITION_COLUMNS)
        if current_partition is None:
            merged_partition = delta_without_partition_cols
        else:
            unchanged_existing_rows = current_partition.join(
                delta_without_partition_cols.select(*FACT_KEYS),
                on=FACT_KEYS,
                how="left_anti",
            )
            merged_partition = unchanged_existing_rows.unionByName(delta_without_partition_cols)

        merged_partition.write.mode("overwrite").parquet(partition_path)
        print(f"Fato atualizada: order_year={order_year}, order_month={order_month}")


def existing_glue_partitions(glue_client, database_name: str, table_name: str):
    paginator = glue_client.get_paginator("get_partitions")
    partitions = set()
    for page in paginator.paginate(DatabaseName=database_name, TableName=table_name):
        for partition in page["Partitions"]:
            partitions.add(tuple(partition["Values"]))
    return partitions


def discover_fact_partitions(bucket: str, prefix: str, already_registered: set):
    s3 = boto3.client("s3")
    discovered = []
    years = s3.list_objects_v2(Bucket=bucket, Prefix=prefix, Delimiter="/")

    for year_prefix in years.get("CommonPrefixes", []):
        year_path = year_prefix["Prefix"]
        year_value = year_path.rstrip("/").split("=")[-1]
        months = s3.list_objects_v2(Bucket=bucket, Prefix=year_path, Delimiter="/")

        for month_prefix in months.get("CommonPrefixes", []):
            month_path = month_prefix["Prefix"]
            month_value = month_path.rstrip("/").split("=")[-1]
            partition_key = (year_value, month_value)

            if partition_key in already_registered:
                continue

            discovered.append(
                {
                    "Values": [year_value, month_value],
                    "StorageDescriptor": {
                        "Location": f"s3://{bucket}/{month_path}",
                        "InputFormat": "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat",
                        "OutputFormat": "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat",
                        "SerdeInfo": {
                            "SerializationLibrary": (
                                "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
                            ),
                        },
                    },
                }
            )

    return discovered


def register_new_partitions():
    glue_client = boto3.client("glue", region_name=boto3.session.Session().region_name)
    current_partitions = existing_glue_partitions(glue_client, GLUE_DATABASE, FACT_TABLE)
    new_partitions = discover_fact_partitions(
        bucket=S3_BUCKET,
        prefix=f"analytics/{FACT_TABLE}/",
        already_registered=current_partitions,
    )

    for batch_start in range(0, len(new_partitions), 25):
        glue_client.batch_create_partition(
            DatabaseName=GLUE_DATABASE,
            TableName=FACT_TABLE,
            PartitionInputList=new_partitions[batch_start : batch_start + 25],
        )

    print(f"Novas particoes registradas no Glue Catalog: {len(new_partitions)}")


def run_incremental_load():
    watermark_date = read_watermark()
    print(f"Watermark de entrada: {watermark_date}")

    orders_delta = read_order_delta(watermark_date)
    delta_count = orders_delta.count()
    print(f"Pedidos novos encontrados: {delta_count}")

    if delta_count == 0:
        print("Sem pedidos novos. Encerrando sem avancar o watermark.")
        return

    source_tables = {
        "orderdetails": read_table("orderdetails"),
        "customers": read_table("customers"),
        "products": read_table("products"),
        "productlines": read_table("productlines"),
        "offices": read_table("offices"),
        "employees": read_table("employees"),
    }

    dimensions = build_dimensions(orders_delta, source_tables)
    fact_delta = build_fact_delta(orders_delta, source_tables["orderdetails"], dimensions)
    max_order_date = str(orders_delta.agg(F.max("orderDate")).first()[0])

    write_dimensions(dimensions)
    merge_fact_partitions(fact_delta)
    register_new_partitions()
    update_watermark("SUCCEEDED", max_order_date=max_order_date)

    print(f"Watermark atualizado para {max_order_date}. Job concluido com sucesso.")


try:
    run_incremental_load()
except Exception as exc:
    print(f"Falha no job incremental: {exc}")
    try:
        update_watermark("FAILED")
    except Exception as watermark_error:
        print(f"Nao foi possivel marcar o watermark como FAILED: {watermark_error}")
    raise
finally:
    job.commit()
