import sys
import json
import time
import boto3
import pymysql
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from awsglue.context import GlueContext
from awsglue.job import Job


def log(msg):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[ETL][{ts}] {msg}", flush=True)


PIPELINE_NAME = "classicmodels_sales"

log("STAGE 0 — resolving job args")
args = getResolvedOptions(sys.argv, ["JOB_NAME", "SECRET_ARN", "S3_BUCKET", "CATALOG_DATABASE"])
log(f"JOB_NAME={args['JOB_NAME']} S3_BUCKET={args['S3_BUCKET']} CATALOG_DATABASE={args['CATALOG_DATABASE']}")

log("STAGE 1 — init Spark / GlueContext")
sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)
job.init(args["JOB_NAME"], args)
log("Spark + Glue context ready")

# ── credentials ───────────────────────────────────────────────────────────────
log("STAGE 2 — fetch secret")
sm = boto3.client("secretsmanager")
secret = json.loads(sm.get_secret_value(SecretId=args["SECRET_ARN"])["SecretString"])
host     = secret["host"]
port     = secret["port"]
user     = secret["username"]
password = secret["password"]
db = secret["dbname"]
log(f"secret resolved host={host} port={port} db={db} user={user}")

jdbc_url = f"jdbc:mysql://{host}:{port}/{db}"
jdbc_opts = {
    "url": jdbc_url,
    "user": user,
    "password": password,
    "driver": "com.mysql.cj.jdbc.Driver",
}

S3 = f"s3://{args['S3_BUCKET']}/analytics"
log(f"S3 output prefix = {S3}")


def path_exists(path):
    """True se o prefixo S3 já tem algum objeto (usado para checar partições/tabelas já gravadas)."""
    jvm = sc._jvm
    fs = jvm.org.apache.hadoop.fs.FileSystem.get(jvm.java.net.URI(path), sc._jsc.hadoopConfiguration())
    return fs.exists(jvm.org.apache.hadoop.fs.Path(path))


# ── watermark (pymysql — fora do Spark, é um valor escalar) ────────────────────
def db_connect():
    return pymysql.connect(
        host=host, user=user, password=password, port=int(port), database=db, autocommit=False,
    )


def get_watermark():
    conn = db_connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT last_processed_order_date, last_run_status "
                "FROM etl_watermark WHERE pipeline_name = %s",
                (PIPELINE_NAME,),
            )
            return cur.fetchone()
    finally:
        conn.close()


def update_watermark(status, last_processed_order_date=None):
    conn = db_connect()
    try:
        with conn.cursor() as cur:
            if last_processed_order_date is not None:
                cur.execute(
                    "UPDATE etl_watermark "
                    "SET last_processed_order_date=%s, last_run_at=UTC_TIMESTAMP(), last_run_status=%s "
                    "WHERE pipeline_name=%s",
                    (last_processed_order_date, status, PIPELINE_NAME),
                )
            else:
                cur.execute(
                    "UPDATE etl_watermark SET last_run_at=UTC_TIMESTAMP(), last_run_status=%s "
                    "WHERE pipeline_name=%s",
                    (status, PIPELINE_NAME),
                )
        conn.commit()
    finally:
        conn.close()


log("STAGE 2.5 — read watermark")
last_date, last_status = get_watermark()
is_bootstrap = last_status in (None, "NEVER_RUN")
log(f"watermark: last_processed_order_date={last_date} last_run_status={last_status} bootstrap={is_bootstrap}")


# ── extract ───────────────────────────────────────────────────────────────────
log("STAGE 3 — extract tables from MySQL via JDBC")


def read_table(table):
    t0 = time.time()
    log(f"  reading table `{table}` ...")
    df = spark.read.format("jdbc").options(**jdbc_opts, dbtable=table).load()
    n = df.count()
    log(f"  read `{table}` rows={n} elapsed={time.time()-t0:.1f}s")
    return df


def read_in(table, col, values):
    """Lê de `table` apenas as linhas cujo `col` está em `values`."""
    if not values:
        sub = f"(SELECT * FROM {table} WHERE 1=0) AS t"
    else:
        in_list = ", ".join(
            str(v) if isinstance(v, int) else "'%s'" % str(v).replace("'", "''")
            for v in values
        )
        sub = f"(SELECT * FROM {table} WHERE {col} IN ({in_list})) AS t"
    log(f"  reading `{table}` filtered by {col} ({len(values)} affected key[s]) ...")
    return spark.read.format("jdbc").options(**jdbc_opts, dbtable=sub).load()

if is_bootstrap:
    orders = read_table("orders")
    orderdetails = read_table("orderdetails")
    customers = read_table("customers")
    products = read_table("products")
else:
    log(f"  reading `orders` delta (orderDate > {last_date.isoformat()}) ...")
    t0 = time.time()
    orders = spark.read.format("jdbc").options(
        **jdbc_opts,
        dbtable=f"(SELECT * FROM orders WHERE orderDate > '{last_date.isoformat()}') AS o",
    ).load()
    n = orders.count()
    log(f"  read `orders` delta rows={n} elapsed={time.time()-t0:.1f}s")

    # chaves afetadas: pedidos -> clientes; itens dos pedidos -> produtos
    order_nums = [r[0] for r in orders.select("orderNumber").distinct().collect()]
    orderdetails = read_in("orderdetails", "orderNumber", order_nums)
    affected_custs = [r[0] for r in orders.select("customerNumber").distinct().collect()]
    affected_prods = [r[0] for r in orderdetails.select("productCode").distinct().collect()]
    customers = read_in("customers", "customerNumber", affected_custs)
    products = read_in("products", "productCode", affected_prods)

# tabelas de apoio (pequenas, sem chave por pedido) — sempre completas
productlines = read_table("productlines")
offices = read_table("offices")
employees = read_table("employees")

log("STAGE 3 done — all source tables loaded")

# ── transform ─────────────────────────────────────────────────────────────────
log("STAGE 4 — transformations")
from pyspark.sql import functions as F

# dim_customers — tabela mestre, reconstruída por completo a cada run
log("building dim_customers")
dim_customers = customers.join(
    employees.select(
        F.col("employeeNumber"),
        F.col("officeCode"),
    ),
    customers["salesRepEmployeeNumber"] == employees["employeeNumber"],
    "left",
).join(
    offices.select("officeCode", "territory"),
    "officeCode",
    "left",
).select(
    F.col("customerNumber").alias("customer_id"),
    F.col("customerName").alias("customer_name"),
    F.concat_ws(" ", F.col("contactFirstName"), F.col("contactLastName")).alias("contact_name"),
    F.col("city"),
    F.col("country"),
    F.col("territory"),
)

# dim_products — tabela mestre, reconstruída por completo a cada run
log("building dim_products")
dim_products = products.join(productlines, "productLine", "left").select(
    F.col("productCode").alias("product_id"),
    F.col("productName").alias("product_name"),
    F.col("productLine").alias("product_line"),
    F.col("productVendor").alias("product_vendor"),
)

# country é a PK natural; agrega o primeiro territory não-nulo por país,
# evitando duplicar linhas quando reps de territórios diferentes atendem o mesmo país.
log("building dim_countries")
dim_countries = customers.join(
    employees.select("employeeNumber", "officeCode"),
    customers["salesRepEmployeeNumber"] == employees["employeeNumber"],
    "left",
).join(
    offices.select("officeCode", "territory"),
    "officeCode",
    "left",
).groupBy("country").agg(
    F.first("territory", ignorenulls=True).alias("territory"),
).withColumn(
    "country_key", F.md5(F.col("country"))
)

# dim_dates — derivado do `orders` (delta ou completo no bootstrap).
log("building dim_dates")
dim_dates = orders.select(F.col("orderDate").alias("full_date")).distinct().withColumn(
    "date_key",  F.date_format(F.col("full_date"), "yyyyMMdd").cast("int"),
    ).withColumn("year",    F.year("full_date")
    ).withColumn("quarter", F.quarter("full_date")
    ).withColumn("month",   F.month("full_date")
    ).withColumn("day",     F.dayofmonth("full_date")
).select("date_key", "full_date", "year", "quarter", "month", "day")

# fact_orders — só o delta de pedidos (ou tudo, no bootstrap)
log("building fact_orders")
# Use using-column join ("customerNumber") to avoid ambiguous column from orders+customers.
fact_base = (
    orderdetails
    .join(orders, "orderNumber")
    .join(customers.select("customerNumber", "country"), "customerNumber", "left")
    .join(dim_countries.select("country", "country_key"), "country", "left")
)

fact_orders = fact_base.select(
    F.col("orderNumber").alias("order_id"),
    F.col("customerNumber").alias("customer_id"),
    F.col("productCode").alias("product_id"),
    F.date_format(F.col("orderDate"), "yyyyMMdd").cast("int").alias("order_date_key"),
    F.col("country_key"),
    F.col("quantityOrdered").alias("quantity_ordered"),
    F.col("priceEach").alias("price_each"),
    (F.col("quantityOrdered") * F.col("priceEach")).alias("sales_amount"),
    F.year("orderDate").alias("order_year"),
    F.month("orderDate").alias("order_month"),
)

if not is_bootstrap:
    touched = [
        (r["order_year"], r["order_month"])
        for r in fact_orders.select("order_year", "order_month").distinct().collect()
    ]
    existing_paths = [
        f"{S3}/fact_orders/order_year={y}/order_month={m}/"
        for y, m in touched
        if path_exists(f"{S3}/fact_orders/order_year={y}/order_month={m}/")
    ]
    if existing_paths:
        log(f"  dedup fact_orders against {len(existing_paths)} existing partition(s)")
        existing_keys = spark.read.parquet(*existing_paths).select("order_id", "product_id").distinct()
        fact_orders = fact_orders.join(existing_keys, on=["order_id", "product_id"], how="left_anti")

log("STAGE 4 done — transforms defined (lazy)")


# ── load ──────────────────────────────────────────────────────────────────────
log("STAGE 5 — write parquet to S3 + register Glue Catalog")

from awsglue.dynamicframe import DynamicFrame

CATALOG_DB = args["CATALOG_DATABASE"]


def write_catalog(df, name, partition_keys=None):
    """Escreve Parquet em S3 (append) e registra/atualiza tabela no Glue Catalog."""
    t0 = time.time()
    log(f"  writing {name} → s3 + catalog ({CATALOG_DB}.{name}) ...")
    dyf = DynamicFrame.fromDF(df, glueContext, name)
    sink = glueContext.getSink(
        path=f"{S3}/{name}/",
        connection_type="s3",
        updateBehavior="UPDATE_IN_DATABASE",
        partitionKeys=partition_keys or [],
        enableUpdateCatalog=True,
        transformation_ctx=f"sink_{name}",
    )
    sink.setCatalogInfo(catalogDatabase=CATALOG_DB, catalogTableName=name)
    sink.setFormat("glueparquet")
    sink.writeFrame(dyf)
    log(f"  wrote {name} elapsed={time.time()-t0:.1f}s")


def purge_and_write(df, name):
    """Purga o prefixo e reescreve (o sink do Glue só faz append)."""
    path = f"{S3}/{name}/"
    log(f"  purging {path} before full rewrite ...")
    glueContext.purge_s3_path(path, options={"retentionPeriod": 0})
    write_catalog(df, name)


def upsert_dimension(new_df, name, key):
    """Upsert por `key`: remove do histórico as chaves presentes em `new_df`
    e regrava por cima."""
    if not is_bootstrap and path_exists(f"{S3}/{name}/"):
        existing = spark.read.parquet(f"{S3}/{name}/")
        kept = existing.join(new_df.select(key).distinct(), key, "left_anti")
        new_df = new_df.unionByName(kept)
    purge_and_write(new_df, name)


try:
    write_catalog(fact_orders, "fact_orders", partition_keys=["order_year", "order_month"])
    upsert_dimension(dim_dates, "dim_dates", "date_key")
    upsert_dimension(dim_customers, "dim_customers", "customer_id")
    upsert_dimension(dim_products, "dim_products", "product_id")
    upsert_dimension(dim_countries, "dim_countries", "country")
    log("STAGE 5 done — Parquet + Catalog atualizados")

    new_max_date = orders.agg(F.max("orderDate")).first()[0]
    final_date = new_max_date or last_date
    log(f"STAGE 6 — updating watermark: status=SUCCEEDED last_processed_order_date={final_date}")
    update_watermark("SUCCEEDED", final_date)

    job.commit()
    log("ETL FINISHED OK")
except Exception:
    log("ETL FAILED — marking watermark as FAILED (sem avançar a data)")
    update_watermark("FAILED")
    raise
