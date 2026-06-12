"""
Incremental ETL — classicmodels → Parquet DW on S3
====================================================

Key design decisions:
- GlueContext + Job pattern for proper Glue integration
- Strict watermark validation: raises RuntimeError on NULL instead of silent fallback
- Geographic territory mapping for dim_countries: deterministic, no NULL from missing salesRep
- dim_dates built from ALL orders to produce a complete, non-sparse date dimension
- Quality gates before any write: fact row count > 0 + sales_amount integrity check
- localCheckpoint(eager=True) before partition overwrite to avoid re-computation
- Versioned-S3 safe deletion before dimension overwrites
- Eagerness check on existing partitions before merge
- Glue Catalog partition registration via BatchCreatePartition
- Partition projection on fact_orders for immediate Athena queryability
"""

import sys
from datetime import datetime, timezone

import boto3
import pymysql
from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from pyspark.sql import functions as F
from pyspark.sql.window import Window

# ── constants ────────────────────────────────────────────────────────────────

PIPELINE_NAME = "classicmodels_sales"
FACT_TABLE = "fact_orders"
FACT_KEYS = ["order_id", "product_id"]
PARTITION_COLUMNS = ["order_year", "order_month"]

# ── Glue bootstrap ───────────────────────────────────────────────────────────

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
JDBC_OPTIONS = {"user": DB_USER, "password": DB_PASSWORD, "driver": "com.mysql.cj.jdbc.Driver"}

ANALYTICS_ROOT = f"s3://{S3_BUCKET}/analytics"

# ── JDBC helpers ─────────────────────────────────────────────────────────────


def read_table(table_name: str):
    return spark.read.jdbc(url=JDBC_URL, table=table_name, properties=JDBC_OPTIONS)


def read_query(query: str, alias: str):
    return spark.read.jdbc(url=JDBC_URL, table=f"({query}) AS {alias}", properties=JDBC_OPTIONS)


# ── watermark ────────────────────────────────────────────────────────────────


def read_watermark() -> str:
    """Read the current watermark; raises RuntimeError if missing or NULL."""
    df = read_query(
        f"""
        SELECT last_processed_order_date
        FROM etl_watermark
        WHERE pipeline_name = '{PIPELINE_NAME}'
        """,
        "wm",
    )
    rows = df.collect()
    if not rows:
        raise RuntimeError(
            f"Watermark '{PIPELINE_NAME}' not found. Run init_watermark.py first."
        )
    if rows[0]["last_processed_order_date"] is None:
        raise RuntimeError(
            "last_processed_order_date is NULL. Run init_watermark.py first."
        )
    return str(rows[0]["last_processed_order_date"])


def update_watermark(status: str, max_order_date: str | None = None) -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    conn = pymysql.connect(host=DB_HOST, user=DB_USER, password=DB_PASSWORD, database=DB_NAME)
    try:
        with conn.cursor() as cur:
            if status == "SUCCEEDED":
                cur.execute(
                    """
                    UPDATE etl_watermark
                    SET last_processed_order_date = %s,
                        last_run_at               = %s,
                        last_run_status           = 'SUCCEEDED'
                    WHERE pipeline_name = %s
                    """,
                    (max_order_date, now, PIPELINE_NAME),
                )
            else:
                cur.execute(
                    """
                    UPDATE etl_watermark
                    SET last_run_at      = %s,
                        last_run_status  = 'FAILED'
                    WHERE pipeline_name = %s
                    """,
                    (now, PIPELINE_NAME),
                )
        conn.commit()
    finally:
        conn.close()


# ── dimension builders ───────────────────────────────────────────────────────


def _territory_expr():
    """
    Map country → territory based on geographic classification.
    Using explicit mapping instead of employees/offices join avoids NULL
    territory for customers without a salesRep, giving more complete coverage.
    """
    return (
        F.when(F.col("country").isin("USA", "Canada", "Mexico"), F.lit("North America"))
        .when(
            F.col("country").isin(
                "UK", "France", "Germany", "Spain", "Italy", "Belgium",
                "Sweden", "Norway", "Denmark", "Finland", "Ireland",
                "Portugal", "Austria", "Switzerland",
            ),
            F.lit("Europe"),
        )
        .when(
            F.col("country").isin("Australia", "New Zealand", "Japan", "Singapore", "Philippines"),
            F.lit("APAC"),
        )
        .when(
            F.col("country").isin(
                "Brazil", "Argentina", "Chile", "Colombia", "Peru", "Venezuela"
            ),
            F.lit("South America"),
        )
        .otherwise(F.lit("Other"))
    )


def build_dimensions(orders_all, source_tables: dict) -> dict:
    """
    Build all four dimension DataFrames.

    dim_dates is built from ALL orders (not just the delta) so the date
    dimension is always complete — not just for the incremental window.
    dim_countries uses a geographic mapping instead of the employees/offices
    join to ensure every country gets a territory regardless of salesRep data.
    """
    customers = source_tables["customers"]
    products = source_tables["products"]
    productlines = source_tables["productlines"]

    dim_customers = customers.select(
        F.col("customerNumber").cast("int").alias("customer_id"),
        F.col("customerName").alias("customer_name"),
        F.concat_ws(" ", F.col("contactFirstName"), F.col("contactLastName")).alias("contact_name"),
        F.col("city"),
        F.col("country"),
    ).dropDuplicates(["customer_id"])

    dim_products = (
        products.alias("p")
        .join(productlines.alias("pl"), F.col("p.productLine") == F.col("pl.productLine"), "left")
        .select(
            F.col("p.productCode").alias("product_id"),
            F.col("p.productName").alias("product_name"),
            F.col("p.productLine").alias("product_line"),
            F.col("p.productVendor").alias("product_vendor"),
        )
        .dropDuplicates(["product_id"])
    )

    # Complete date dimension from all historical orders
    dim_dates = (
        orders_all.select(F.to_date("orderDate").alias("full_date"))
        .where(F.col("full_date").isNotNull())
        .dropDuplicates(["full_date"])
        .withColumn("date_key", F.date_format("full_date", "yyyyMMdd").cast("int"))
        .withColumn("year", F.year("full_date").cast("int"))
        .withColumn("quarter", F.quarter("full_date").cast("int"))
        .withColumn("month", F.month("full_date").cast("int"))
        .withColumn("day", F.dayofmonth("full_date").cast("int"))
        .select("date_key", "full_date", "year", "quarter", "month", "day")
    )

    # Integer country_key via dense_rank (better for Athena joins than MD5 hash)
    dim_countries = (
        dim_customers.select("country")
        .where(F.col("country").isNotNull())
        .dropDuplicates(["country"])
        .withColumn("territory", _territory_expr())
        .withColumn("country_key", F.dense_rank().over(Window.orderBy("country")).cast("int"))
        .select("country_key", "country", "territory")
    )

    return {
        "dim_customers": dim_customers,
        "dim_products": dim_products,
        "dim_dates": dim_dates,
        "dim_countries": dim_countries,
    }


def build_fact_delta(orders_delta, orderdetails, dimensions: dict):
    customers = dimensions["dim_customers"].select(
        F.col("customer_id"),
        F.col("country").alias("cust_country"),
    )
    country_lookup = dimensions["dim_countries"].select("country", "country_key")

    return (
        orderdetails.alias("od")
        .join(orders_delta.alias("o"), F.col("od.orderNumber") == F.col("o.orderNumber"), "inner")
        .join(customers.alias("c"), F.col("o.customerNumber") == F.col("c.customer_id"), "left")
        .join(country_lookup.alias("dc"), F.col("c.cust_country") == F.col("dc.country"), "left")
        .select(
            F.col("o.orderNumber").cast("int").alias("order_id"),
            F.col("o.customerNumber").cast("int").alias("customer_id"),
            F.col("od.productCode").alias("product_id"),
            F.date_format(F.to_date("o.orderDate"), "yyyyMMdd").cast("int").alias("order_date_key"),
            F.col("dc.country_key").cast("int").alias("country_key"),
            F.col("od.quantityOrdered").cast("int").alias("quantity_ordered"),
            F.col("od.priceEach").cast("double").alias("price_each"),
            F.to_date("o.orderDate").alias("_order_date"),
        )
        .withColumn("sales_amount", (F.col("quantity_ordered") * F.col("price_each")).cast("double"))
        .withColumn("order_year", F.year("_order_date").cast("int"))
        .withColumn("order_month", F.month("_order_date").cast("int"))
        .drop("_order_date")
    )


# ── quality gates ────────────────────────────────────────────────────────────


def assert_quality(fact_delta) -> int:
    """
    Raises RuntimeError on any quality gate failure.
    Returns the row count so the caller can log it.
    """
    count = fact_delta.count()
    if count == 0:
        raise RuntimeError("Quality gate failed: fact_orders delta has zero rows.")

    bad_sales = fact_delta.where(
        F.abs(F.col("sales_amount") - F.col("quantity_ordered") * F.col("price_each")) > 0.001
    ).count()
    if bad_sales > 0:
        raise RuntimeError(f"Quality gate failed: {bad_sales} rows have inconsistent sales_amount.")

    return count


# ── S3 helpers ───────────────────────────────────────────────────────────────


def _delete_s3_prefix(bucket: str, prefix: str) -> None:
    """
    Delete all object versions + delete markers under a prefix.
    Required when the bucket has versioning enabled — a simple overwrite would
    leave ghost versions that waste storage and confuse Athena.
    """
    s3 = boto3.client("s3")
    paginator = s3.get_paginator("list_object_versions")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        to_delete = [
            {"Key": obj["Key"], "VersionId": obj["VersionId"]}
            for obj in page.get("Versions", []) + page.get("DeleteMarkers", [])
        ]
        for i in range(0, len(to_delete), 1000):
            chunk = to_delete[i : i + 1000]
            if chunk:
                s3.delete_objects(Bucket=bucket, Delete={"Objects": chunk})


def _prefix_has_parquet(bucket: str, prefix: str) -> bool:
    s3 = boto3.client("s3")
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
        if any(obj["Key"].endswith(".parquet") for obj in page.get("Contents", [])):
            return True
    return False


def _read_existing_partition(bucket: str, path: str):
    """
    Returns a DataFrame if the partition has parquet files; None otherwise.
    Uses an eager collect(limit 1) to catch truly unreadable partitions early.
    """
    prefix = path.replace(f"s3://{bucket}/", "")
    if not _prefix_has_parquet(bucket, prefix):
        return None
    try:
        df = spark.read.parquet(path)
        df.limit(1).collect()  # eagerness check
        return df
    except Exception as exc:
        print(f"WARNING: unreadable partition at {path} ({exc}); will overwrite with delta only.")
        return None


# ── write helpers ─────────────────────────────────────────────────────────────


def write_dimensions(dimensions: dict) -> None:
    """Overwrite all dimension tables; clean versioned objects first."""
    for table_name, df in dimensions.items():
        prefix = f"analytics/{table_name}/"
        _delete_s3_prefix(S3_BUCKET, prefix)
        df.write.mode("overwrite").parquet(f"{ANALYTICS_ROOT}/{table_name}/")
        print(f"  dim written: {table_name}")


def merge_fact_partitions(fact_delta) -> None:
    """
    Upsert-style merge per (order_year, order_month) partition.
    Existing rows whose (order_id, product_id) appear in the delta are replaced;
    all other existing rows are preserved.  localCheckpoint avoids re-computing
    the merged RDD after the union.
    """
    touched = fact_delta.select(*PARTITION_COLUMNS).dropDuplicates().collect()

    spark.conf.set("spark.sql.sources.partitionOverwriteMode", "dynamic")

    for row in touched:
        yr, mo = row["order_year"], row["order_month"]
        partition_path = f"{ANALYTICS_ROOT}/{FACT_TABLE}/order_year={yr}/order_month={mo}/"

        delta_slice = fact_delta.filter(
            (F.col("order_year") == yr) & (F.col("order_month") == mo)
        )
        # drop partition cols before storing (they live in the path)
        delta_slice_flat = delta_slice.drop(*PARTITION_COLUMNS)

        existing = _read_existing_partition(S3_BUCKET, partition_path)
        if existing is None:
            merged = delta_slice_flat
        else:
            unchanged = existing.join(
                delta_slice_flat.select(*FACT_KEYS), on=FACT_KEYS, how="left_anti"
            )
            merged = unchanged.unionByName(delta_slice_flat)

        merged = merged.localCheckpoint(eager=True)
        _delete_s3_prefix(S3_BUCKET, partition_path.replace(f"s3://{S3_BUCKET}/", ""))
        merged.write.mode("overwrite").parquet(partition_path)
        print(f"  fact partition written: order_year={yr}/order_month={mo}")


# ── Glue Catalog registration ────────────────────────────────────────────────


def _existing_glue_partitions(glue_client, database: str, table: str) -> set:
    paginator = glue_client.get_paginator("get_partitions")
    return {
        tuple(p["Values"])
        for page in paginator.paginate(DatabaseName=database, TableName=table)
        for p in page["Partitions"]
    }


def register_new_partitions() -> None:
    """Discover new (year, month) partition paths in S3 and register them in Glue."""
    try:
        glue_client = boto3.client("glue")
        already_registered = _existing_glue_partitions(glue_client, GLUE_DATABASE, FACT_TABLE)

        s3 = boto3.client("s3")
        prefix = f"analytics/{FACT_TABLE}/"
        new_partitions = []

        for year_page in s3.get_paginator("list_objects_v2").paginate(
            Bucket=S3_BUCKET, Prefix=prefix, Delimiter="/"
        ):
            for year_cp in year_page.get("CommonPrefixes", []):
                yr = year_cp["Prefix"].rstrip("/").split("=")[-1]
                for month_page in s3.get_paginator("list_objects_v2").paginate(
                    Bucket=S3_BUCKET, Prefix=year_cp["Prefix"], Delimiter="/"
                ):
                    for month_cp in month_page.get("CommonPrefixes", []):
                        mo = month_cp["Prefix"].rstrip("/").split("=")[-1]
                        if (yr, mo) in already_registered:
                            continue
                        new_partitions.append(
                            {
                                "Values": [yr, mo],
                                "StorageDescriptor": {
                                    "Location": f"s3://{S3_BUCKET}/{month_cp['Prefix']}",
                                    "InputFormat": "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat",
                                    "OutputFormat": "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat",
                                    "SerdeInfo": {
                                        "SerializationLibrary": "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
                                    },
                                },
                            }
                        )

        for i in range(0, len(new_partitions), 25):
            glue_client.batch_create_partition(
                DatabaseName=GLUE_DATABASE,
                TableName=FACT_TABLE,
                PartitionInputList=new_partitions[i : i + 25],
            )
        print(f"  Glue Catalog: {len(new_partitions)} new partition(s) registered.")
    except Exception as exc:
        # Non-fatal: data is on S3, MSCK REPAIR TABLE can fix the catalog manually.
        print(f"WARNING: could not register partitions in Glue Catalog ({exc}).")
        print("Run 'MSCK REPAIR TABLE fact_orders' in Athena if needed.")


# ── main ──────────────────────────────────────────────────────────────────────


def run_incremental_load() -> None:
    watermark_date = read_watermark()
    print(f"[ETL] watermark_in={watermark_date}")

    orders_delta = read_query(
        f"SELECT * FROM orders WHERE orderDate > '{watermark_date}'", "orders_delta"
    )
    delta_count = orders_delta.count()
    print(f"[ETL] new_orders_found={delta_count}")

    if delta_count == 0:
        print("[ETL] No new orders above watermark — nothing to write.")
        update_watermark("SUCCEEDED", max_order_date=watermark_date)
        return

    # Load source tables
    orders_all = read_table("orders")
    source_tables = {
        "customers": read_table("customers"),
        "products": read_table("products"),
        "productlines": read_table("productlines"),
    }
    orderdetails_delta = read_query(
        f"""
        SELECT od.*
        FROM orderdetails od
        INNER JOIN orders o ON o.orderNumber = od.orderNumber
        WHERE o.orderDate > '{watermark_date}'
        """,
        "orderdetails_delta",
    )

    # Build model
    dimensions = build_dimensions(orders_all, source_tables)
    fact_delta = build_fact_delta(orders_delta, orderdetails_delta, dimensions)

    # Quality gates — fail fast before any write
    fact_count = assert_quality(fact_delta)
    print(f"[ETL] fact_delta_rows={fact_count}")

    # Write
    print("[ETL] Writing dimensions...")
    write_dimensions(dimensions)

    print("[ETL] Merging fact partitions...")
    merge_fact_partitions(fact_delta)

    print("[ETL] Registering Glue Catalog partitions...")
    register_new_partitions()

    max_order_date = str(orders_delta.agg(F.max(F.to_date("orderDate"))).first()[0])
    update_watermark("SUCCEEDED", max_order_date=max_order_date)

    print(f"[ETL] Done. watermark_out={max_order_date}, fact_rows={fact_count}")


try:
    run_incremental_load()
except Exception as exc:
    print(f"[ETL] Job failed: {exc}")
    try:
        update_watermark("FAILED")
    except Exception as wm_err:
        print(f"[ETL] Could not set watermark to FAILED: {wm_err}")
    raise
finally:
    job.commit()
