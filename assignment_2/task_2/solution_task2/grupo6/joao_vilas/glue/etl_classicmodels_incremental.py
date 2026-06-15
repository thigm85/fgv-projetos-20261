import json
import sys
from datetime import datetime, timezone

import boto3
import pymysql
from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from pyspark.sql import functions as F
from pyspark.sql.utils import AnalysisException
from pyspark.sql.window import Window


args = getResolvedOptions(
    sys.argv,
    [
        "JOB_NAME",
        "connection_name",
        "output_s3_path",
        "secret_id",
        "pipeline_name",
        "region",
    ],
)

sc = SparkContext()
glue_context = GlueContext(sc)
spark = glue_context.spark_session

job = Job(glue_context)
job.init(args["JOB_NAME"], args)

OUTPUT_PREFIX = args["output_s3_path"].rstrip("/")
FACT_TABLE = "fact_orders"
PARTITION_COLS = ["order_year", "order_month"]
BUSINESS_KEYS = ["order_id", "product_id"]


def get_db_credentials() -> dict:
    client = boto3.client("secretsmanager", region_name=args["region"])
    secret = client.get_secret_value(SecretId=args["secret_id"])
    return json.loads(secret["SecretString"])


def watermark_connection():
    creds = get_db_credentials()
    return pymysql.connect(
        host=creds["host"],
        port=int(creds["port"]),
        user=creds["username"],
        password=creds["password"],
        database=creds["dbname"],
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )


def read_watermark(conn) -> dict:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT last_processed_order_date, last_run_status
            FROM etl_watermark
            WHERE pipeline_name = %s
            """,
            (args["pipeline_name"],),
        )
        row = cursor.fetchone()
    if not row:
        raise RuntimeError(
            f"Watermark '{args['pipeline_name']}' ausente. Rode init_watermark (Task 1)."
        )
    return row


def update_watermark_success(conn, max_processed_date) -> None:
    """Avança o watermark (nunca retrocede) e marca SUCCEEDED."""
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    with conn.cursor() as cursor:
        cursor.execute(
            """
            UPDATE etl_watermark
            SET last_processed_order_date = GREATEST(
                    COALESCE(last_processed_order_date, %s), %s
                ),
                last_run_at = %s,
                last_run_status = 'SUCCEEDED'
            WHERE pipeline_name = %s
            """,
            (max_processed_date, max_processed_date, now_utc, args["pipeline_name"]),
        )
    print(f"[WATERMARK] SUCCEEDED — last_processed_order_date >= {max_processed_date}")


def update_watermark_no_change(conn) -> None:
    """Sem delta: registra a execução bem-sucedida sem mover a data."""
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    with conn.cursor() as cursor:
        cursor.execute(
            """
            UPDATE etl_watermark
            SET last_run_at = %s, last_run_status = 'SUCCEEDED'
            WHERE pipeline_name = %s
            """,
            (now_utc, args["pipeline_name"]),
        )
    print("[WATERMARK] SUCCEEDED — sem novos pedidos, data inalterada")


def mark_watermark_failed() -> None:
    """Best-effort: marca FAILED sem avançar a data processada."""
    try:
        conn = watermark_connection()
        now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        with conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE etl_watermark
                SET last_run_at = %s, last_run_status = 'FAILED'
                WHERE pipeline_name = %s
                """,
                (now_utc, args["pipeline_name"]),
            )
        conn.close()
        print("[WATERMARK] FAILED — data processada preservada")
    except Exception as exc:  # noqa: BLE001 - log e segue para propagar a falha original
        print(f"[WATERMARK] Não foi possível marcar FAILED: {exc}")


def read_jdbc(dbtable: str, ctx: str):
    print(f"[EXTRACT] JDBC dbtable={dbtable}")
    return glue_context.create_dynamic_frame.from_options(
        connection_type="mysql",
        connection_options={
            "useConnectionProperties": "true",
            "connectionName": args["connection_name"],
            "dbtable": dbtable,
        },
        transformation_ctx=ctx,
    ).toDF()


def assert_no_missing_fk(fact_df, dim_df, fact_key, dim_key, description) -> None:
    missing = (
        fact_df.select(F.col(fact_key).alias("fk"))
        .distinct()
        .join(
            dim_df.select(F.col(dim_key).alias("dk")).distinct(),
            F.col("fk") == F.col("dk"),
            "left_anti",
        )
        .count()
    )
    if missing != 0:
        raise RuntimeError(f"[VALIDATION] FK inválida em {description}: {missing} sem dimensão")
    print(f"[VALIDATION] FK OK: {description}")


def write_dim(df, table_name: str) -> None:
    path = f"{OUTPUT_PREFIX}/{table_name}/"
    print(f"[LOAD] Overwrite dimensão {table_name} -> {path}")
    df.coalesce(1).write.mode("overwrite").format("parquet").save(path)


def write_fact(delta_fact, full_load: bool) -> None:
    fact_path = f"{OUTPUT_PREFIX}/{FACT_TABLE}"

    if full_load:
        print(f"[LOAD] FULL overwrite particionado de {FACT_TABLE} -> {fact_path}")
        spark.conf.set("spark.sql.sources.partitionOverwriteMode", "static")
        (
            delta_fact.write.mode("overwrite")
            .partitionBy(*PARTITION_COLS)
            .format("parquet")
            .save(fact_path)
        )
        return

    spark.conf.set("spark.sql.sources.partitionOverwriteMode", "dynamic")

    affected = [
        (row["order_year"], row["order_month"])
        for row in delta_fact.select(*PARTITION_COLS).distinct().collect()
    ]
    print(f"[LOAD] Partições afetadas: {affected}")

    try:
        existing = spark.read.option("basePath", fact_path).parquet(fact_path)
        condition = None
        for year, month in affected:
            pair = (F.col("order_year") == year) & (F.col("order_month") == month)
            condition = pair if condition is None else (condition | pair)
        existing_affected = existing.where(condition)
        # delta vence em caso de reprocessamento da mesma chave de negócio
        existing_minus = existing_affected.join(delta_fact, BUSINESS_KEYS, "left_anti")
        merged = existing_minus.unionByName(delta_fact)
        print("[LOAD] Merge com partições existentes")
    except AnalysisException:
        merged = delta_fact
        print("[LOAD] Sem partições existentes — primeira gravação do delta")

    (
        merged.write.mode("overwrite")
        .partitionBy(*PARTITION_COLS)
        .format("parquet")
        .save(fact_path)
    )


def build_star_schema(orders, orderdetails, customers, products, offices):
    print("[TRANSFORM] dim_customers")
    dim_customers = customers.select(
        F.col("customerNumber").cast("int").alias("customer_id"),
        F.col("customerName").cast("string").alias("customer_name"),
        F.concat_ws(
            " ",
            F.col("contactFirstName").cast("string"),
            F.col("contactLastName").cast("string"),
        ).alias("contact_name"),
        F.col("city").cast("string").alias("city"),
        F.col("country").cast("string").alias("country"),
    ).dropDuplicates(["customer_id"])

    print("[TRANSFORM] dim_products")
    dim_products = products.select(
        F.col("productCode").cast("string").alias("product_id"),
        F.col("productName").cast("string").alias("product_name"),
        F.col("productLine").cast("string").alias("product_line"),
        F.col("productVendor").cast("string").alias("product_vendor"),
    ).dropDuplicates(["product_id"])

    print("[TRANSFORM] dim_dates")
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

    print("[TRANSFORM] dim_countries")
    countries = customers.select(F.col("country").cast("string").alias("country")).distinct()
    office_territory = offices.select(
        F.col("country").cast("string").alias("office_country"),
        F.col("territory").cast("string").alias("territory"),
    ).dropDuplicates(["office_country"])
    dim_countries_base = (
        countries.join(
            office_territory, countries.country == office_territory.office_country, "left"
        )
        .select(
            F.col("country"),
            F.coalesce(F.col("territory"), F.lit("Unknown")).alias("territory"),
        )
        .dropDuplicates(["country"])
    )
    dim_countries = dim_countries_base.withColumn(
        "country_key", F.dense_rank().over(Window.orderBy("country")).cast("int")
    ).select("country_key", "country", "territory")

    print("[TRANSFORM] fact_orders (+ partições order_year/order_month)")
    fact_orders = (
        orders.alias("o")
        .join(orderdetails.alias("od"), F.col("o.orderNumber") == F.col("od.orderNumber"), "inner")
        .join(customers.alias("c"), F.col("o.customerNumber") == F.col("c.customerNumber"), "inner")
        .join(dim_countries.alias("dc"), F.col("c.country") == F.col("dc.country"), "left")
        .select(
            F.col("o.orderNumber").cast("int").alias("order_id"),
            F.col("o.customerNumber").cast("int").alias("customer_id"),
            F.col("od.productCode").cast("string").alias("product_id"),
            F.date_format(F.to_date(F.col("o.orderDate")), "yyyyMMdd").cast("int").alias("order_date_key"),
            F.col("dc.country_key").cast("int").alias("country_key"),
            F.col("od.quantityOrdered").cast("int").alias("quantity_ordered"),
            F.col("od.priceEach").cast("decimal(10,2)").alias("price_each"),
            F.round(
                F.col("od.quantityOrdered").cast("double") * F.col("od.priceEach").cast("double"),
                2,
            ).cast("decimal(18,2)").alias("sales_amount"),
            F.year(F.to_date(F.col("o.orderDate"))).cast("int").alias("order_year"),
            F.month(F.to_date(F.col("o.orderDate"))).cast("int").alias("order_month"),
        )
    )

    return fact_orders, dim_customers, dim_products, dim_dates, dim_countries


def main() -> None:
    wm_conn = watermark_connection()
    watermark = read_watermark(wm_conn)
    wm_date = watermark["last_processed_order_date"]
    wm_status = watermark["last_run_status"]

    full_load = wm_status == "NEVER_RUN" or wm_date is None
    mode = "FULL" if full_load else "INCREMENTAL"
    print(f"[START] modo={mode} | watermark={wm_date} | status={wm_status}")

    if full_load:
        orders_tbl = "orders"
        details_tbl = "orderdetails"
    else:
        wm_str = wm_date.strftime("%Y-%m-%d") if hasattr(wm_date, "strftime") else str(wm_date)
        orders_tbl = f"(SELECT * FROM orders WHERE orderDate > '{wm_str}') AS o_delta"
        details_tbl = (
            "(SELECT od.* FROM orderdetails od "
            "JOIN orders o ON od.orderNumber = o.orderNumber "
            f"WHERE o.orderDate > '{wm_str}') AS od_delta"
        )

    orders = read_jdbc(orders_tbl, "read_orders")
    delta_order_count = orders.count()
    print(f"[EXTRACT] pedidos no escopo deste run: {delta_order_count}")

    if not full_load and delta_order_count == 0:
        print("[INFO] Nenhum pedido novo acima do watermark. Encerrando sem alterar dados.")
        update_watermark_no_change(wm_conn)
        wm_conn.close()
        job.commit()
        return

    orderdetails = read_jdbc(details_tbl, "read_orderdetails")
    customers = read_jdbc("customers", "read_customers")
    products = read_jdbc("products", "read_products")
    offices = read_jdbc("offices", "read_offices")

    fact_orders, dim_customers, dim_products, dim_dates, dim_countries = build_star_schema(
        orders, orderdetails, customers, products, offices
    )

    fact_count = fact_orders.count()
    print(f"[VALIDATION] linhas no delta de fact_orders: {fact_count}")
    if fact_count <= 0:
        raise RuntimeError("[VALIDATION] fact_orders do delta está vazio (orderdetails ausente?)")

    assert_no_missing_fk(fact_orders, dim_customers, "customer_id", "customer_id", "fact->dim_customers")
    assert_no_missing_fk(fact_orders, dim_products, "product_id", "product_id", "fact->dim_products")
    assert_no_missing_fk(fact_orders, dim_dates, "order_date_key", "date_key", "fact->dim_dates")
    assert_no_missing_fk(fact_orders, dim_countries, "country_key", "country_key", "fact->dim_countries")

    sales_errors = fact_orders.where(
        F.abs(
            F.col("sales_amount").cast("double")
            - (F.col("quantity_ordered").cast("double") * F.col("price_each").cast("double"))
        )
        > 0.01
    ).count()
    if sales_errors != 0:
        raise RuntimeError(f"[VALIDATION] sales_amount inconsistente em {sales_errors} registro(s)")
    print("[VALIDATION] sales_amount = quantity_ordered * price_each OK")

    # maior orderDate efetivamente processado neste run
    max_processed_date = orders.select(F.max(F.to_date(F.col("orderDate")))).collect()[0][0]
    print(f"[INFO] MAX(orderDate) processado: {max_processed_date}")

    # dimensões (Opção A: overwrite completo) + fato particionada
    write_dim(dim_customers, "dim_customers")
    write_dim(dim_products, "dim_products")
    write_dim(dim_dates, "dim_dates")
    write_dim(dim_countries, "dim_countries")
    write_fact(fact_orders, full_load=full_load)

    update_watermark_success(wm_conn, max_processed_date)
    wm_conn.close()

    print("[SUCCESS] QUALITY CHECK PASSED")
    print(f"[SUCCESS] ETL {mode} finalizado com sucesso")
    job.commit()


try:
    main()
except Exception:
    print("[ERROR] Falha no ETL incremental — marcando watermark como FAILED")
    mark_watermark_failed()
    raise
