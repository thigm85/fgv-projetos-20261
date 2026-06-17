import sys

from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from pyspark.sql import functions as F
from pyspark.sql.window import Window


args = getResolvedOptions(
    sys.argv,
    [
        "JOB_NAME",
        "connection_name",
        "output_s3_path",
    ],
)

sc = SparkContext()
glue_context = GlueContext(sc)
spark = glue_context.spark_session

job = Job(glue_context)
job.init(args["JOB_NAME"], args)


def read_mysql_table(table_name: str):
    print(f"[EXTRACT] Lendo tabela MySQL: {table_name}")

    return glue_context.create_dynamic_frame.from_options(
        connection_type="mysql",
        connection_options={
            "useConnectionProperties": "true",
            "connectionName": args["connection_name"],
            "dbtable": table_name,
        },
        transformation_ctx=f"read_{table_name}",
    ).toDF()


def assert_non_empty(df, table_name: str) -> None:
    total = df.count()

    if total <= 0:
        raise RuntimeError(f"[VALIDATION] {table_name} está vazia")

    print(f"[VALIDATION] {table_name}: {total} registros")


def assert_no_missing_fk(fact_df, dim_df, fact_key: str, dim_key: str, description: str) -> None:
    missing = (
        fact_df.select(F.col(fact_key).alias("fact_key"))
        .distinct()
        .join(
            dim_df.select(F.col(dim_key).alias("dim_key")).distinct(),
            F.col("fact_key") == F.col("dim_key"),
            "left_anti",
        )
        .count()
    )

    if missing != 0:
        raise RuntimeError(
            f"[VALIDATION] FK inválida em {description}: {missing} chave(s) sem dimensão"
        )

    print(f"[VALIDATION] FK OK: {description}")


def write_parquet(df, table_name: str) -> None:
    output_path = args["output_s3_path"].rstrip("/")
    table_path = f"{output_path}/{table_name}/"

    print(f"[LOAD] Gravando {table_name} em {table_path}")

    (
        df.coalesce(1)
        .write
        .mode("overwrite")
        .format("parquet")
        .save(table_path)
    )


print("[START] Iniciando ETL ClassicModels para Star Schema")

customers = read_mysql_table("customers")
products = read_mysql_table("products")
productlines = read_mysql_table("productlines")
orders = read_mysql_table("orders")
orderdetails = read_mysql_table("orderdetails")
offices = read_mysql_table("offices")

print("[TRANSFORM] Criando dim_customers")

dim_customers = (
    customers.select(
        F.col("customerNumber").cast("int").alias("customer_id"),
        F.col("customerName").cast("string").alias("customer_name"),
        F.concat_ws(
            " ",
            F.col("contactFirstName").cast("string"),
            F.col("contactLastName").cast("string"),
        ).alias("contact_name"),
        F.col("city").cast("string").alias("city"),
        F.col("country").cast("string").alias("country"),
    )
    .dropDuplicates(["customer_id"])
)

print("[TRANSFORM] Criando dim_products")

dim_products = (
    products.select(
        F.col("productCode").cast("string").alias("product_id"),
        F.col("productName").cast("string").alias("product_name"),
        F.col("productLine").cast("string").alias("product_line"),
        F.col("productVendor").cast("string").alias("product_vendor"),
    )
    .dropDuplicates(["product_id"])
)

print("[TRANSFORM] Criando dim_dates")

order_dates = (
    orders.select(F.to_date(F.col("orderDate")).alias("full_date"))
    .where(F.col("full_date").isNotNull())
    .distinct()
)

dim_dates = order_dates.select(
    F.date_format(F.col("full_date"), "yyyyMMdd").cast("int").alias("date_key"),
    F.col("full_date"),
    F.year(F.col("full_date")).cast("int").alias("year"),
    F.quarter(F.col("full_date")).cast("int").alias("quarter"),
    F.month(F.col("full_date")).cast("int").alias("month"),
    F.dayofmonth(F.col("full_date")).cast("int").alias("day"),
)

print("[TRANSFORM] Criando dim_countries")

countries = customers.select(F.col("country").cast("string").alias("country")).distinct()

office_territory = (
    offices.select(
        F.col("country").cast("string").alias("office_country"),
        F.col("territory").cast("string").alias("territory"),
    )
    .dropDuplicates(["office_country"])
)

dim_countries_base = (
    countries.join(
        office_territory,
        countries.country == office_territory.office_country,
        "left",
    )
    .select(
        F.col("country"),
        F.coalesce(F.col("territory"), F.lit("Unknown")).alias("territory"),
    )
    .dropDuplicates(["country"])
)

dim_countries = (
    dim_countries_base.withColumn(
        "country_key",
        F.dense_rank().over(Window.orderBy("country")).cast("int"),
    )
    .select(
        F.col("country_key"),
        F.col("country"),
        F.col("territory"),
    )
)

print("[TRANSFORM] Criando fact_orders")

fact_orders = (
    orders.alias("o")
    .join(
        orderdetails.alias("od"),
        F.col("o.orderNumber") == F.col("od.orderNumber"),
        "inner",
    )
    .join(
        customers.alias("c"),
        F.col("o.customerNumber") == F.col("c.customerNumber"),
        "inner",
    )
    .join(
        dim_countries.alias("dc"),
        F.col("c.country") == F.col("dc.country"),
        "left",
    )
    .select(
        F.col("o.orderNumber").cast("int").alias("order_id"),
        F.col("o.customerNumber").cast("int").alias("customer_id"),
        F.col("od.productCode").cast("string").alias("product_id"),
        F.date_format(F.to_date(F.col("o.orderDate")), "yyyyMMdd")
        .cast("int")
        .alias("order_date_key"),
        F.col("dc.country_key").cast("int").alias("country_key"),
        F.col("od.quantityOrdered").cast("int").alias("quantity_ordered"),
        F.col("od.priceEach").cast("decimal(10,2)").alias("price_each"),
        F.round(
            F.col("od.quantityOrdered").cast("double")
            * F.col("od.priceEach").cast("double"),
            2,
        )
        .cast("decimal(18,2)")
        .alias("sales_amount"),
    )
)

print("[VALIDATION] Iniciando validações objetivas")

assert_non_empty(fact_orders, "fact_orders")
assert_non_empty(dim_customers, "dim_customers")
assert_non_empty(dim_products, "dim_products")
assert_non_empty(dim_dates, "dim_dates")
assert_non_empty(dim_countries, "dim_countries")

assert_no_missing_fk(
    fact_orders,
    dim_customers,
    "customer_id",
    "customer_id",
    "fact_orders.customer_id -> dim_customers.customer_id",
)

assert_no_missing_fk(
    fact_orders,
    dim_products,
    "product_id",
    "product_id",
    "fact_orders.product_id -> dim_products.product_id",
)

assert_no_missing_fk(
    fact_orders,
    dim_dates,
    "order_date_key",
    "date_key",
    "fact_orders.order_date_key -> dim_dates.date_key",
)

assert_no_missing_fk(
    fact_orders,
    dim_countries,
    "country_key",
    "country_key",
    "fact_orders.country_key -> dim_countries.country_key",
)

sales_amount_errors = (
    fact_orders.where(
        F.abs(
            F.col("sales_amount").cast("double")
            - (
                F.col("quantity_ordered").cast("double")
                * F.col("price_each").cast("double")
            )
        )
        > 0.01
    )
    .count()
)

if sales_amount_errors != 0:
    raise RuntimeError(
        f"[VALIDATION] sales_amount inconsistente em {sales_amount_errors} registro(s)"
    )

print("[VALIDATION] Regra sales_amount = quantity_ordered * price_each OK")

print("[LOAD] Gravando tabelas em Parquet")

write_parquet(fact_orders, "fact_orders")
write_parquet(dim_customers, "dim_customers")
write_parquet(dim_products, "dim_products")
write_parquet(dim_dates, "dim_dates")
write_parquet(dim_countries, "dim_countries")

print("[SUCCESS] QUALITY CHECK PASSED")
print("[SUCCESS] ETL finalizado com sucesso")

job.commit()