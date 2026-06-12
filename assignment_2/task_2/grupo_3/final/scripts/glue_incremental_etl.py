import sys
from datetime import datetime, timezone

from awsglue.utils import getResolvedOptions
from pyspark.sql import SparkSession, functions as F
from pyspark.sql.window import Window


PIPELINE_NAME = "classicmodels_sales"


def build_country_territory_expr():
    return (
        F.when(F.col("country").isin("USA", "Canada", "Mexico"), F.lit("North America"))
        .when(
            F.col("country").isin(
                "UK",
                "France",
                "Germany",
                "Spain",
                "Italy",
                "Belgium",
                "Sweden",
                "Norway",
                "Denmark",
                "Finland",
                "Ireland",
                "Portugal",
                "Austria",
                "Switzerland",
            ),
            F.lit("Europe"),
        )
        .when(F.col("country").isin("Australia", "New Zealand", "Japan", "Singapore", "Philippines"), F.lit("APAC"))
        .when(F.col("country").isin("Brazil", "Argentina", "Chile", "Colombia", "Peru", "Venezuela"), F.lit("South America"))
        .otherwise(F.lit("Other"))
    )


def jdbc_table(spark, jdbc_url, jdbc_props, table_or_query):
    return spark.read.jdbc(jdbc_url, table_or_query, properties=jdbc_props)


def execute_update(spark, jdbc_url, user, password, sql, params):
    jvm = spark.sparkContext._gateway.jvm
    jvm.java.lang.Class.forName("com.mysql.cj.jdbc.Driver")
    conn = jvm.java.sql.DriverManager.getConnection(jdbc_url, user, password)
    try:
        stmt = conn.prepareStatement(sql)
        try:
            for index, value in enumerate(params, start=1):
                stmt.setString(index, None if value is None else str(value))
            stmt.executeUpdate()
        finally:
            stmt.close()
    finally:
        conn.close()


def update_watermark_success(spark, jdbc_url, jdbc_props, max_order_date):
    execute_update(
        spark,
        jdbc_url,
        jdbc_props["user"],
        jdbc_props["password"],
        """
        UPDATE etl_watermark
        SET last_processed_order_date = ?,
            last_run_at = ?,
            last_run_status = 'SUCCEEDED'
        WHERE pipeline_name = ?
        """,
        [max_order_date, datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"), PIPELINE_NAME],
    )


def update_watermark_no_delta_success(spark, jdbc_url, jdbc_props):
    execute_update(
        spark,
        jdbc_url,
        jdbc_props["user"],
        jdbc_props["password"],
        """
        UPDATE etl_watermark
        SET last_run_at = ?,
            last_run_status = 'SUCCEEDED'
        WHERE pipeline_name = ?
        """,
        [datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"), PIPELINE_NAME],
    )


def update_watermark_failure(spark, jdbc_url, jdbc_props):
    execute_update(
        spark,
        jdbc_url,
        jdbc_props["user"],
        jdbc_props["password"],
        """
        UPDATE etl_watermark
        SET last_run_at = ?,
            last_run_status = 'FAILED'
        WHERE pipeline_name = ?
        """,
        [datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"), PIPELINE_NAME],
    )


def read_watermark(spark, jdbc_url, jdbc_props):
    watermark = jdbc_table(
        spark,
        jdbc_url,
        jdbc_props,
        f"""(
            SELECT last_processed_order_date, last_run_status
            FROM etl_watermark
            WHERE pipeline_name = '{PIPELINE_NAME}'
        ) wm""",
    ).collect()

    if not watermark:
        raise RuntimeError("Watermark classicmodels_sales not found. Run init_watermark.py first.")
    if watermark[0]["last_processed_order_date"] is None:
        raise RuntimeError("last_processed_order_date is NULL. Run init_watermark.py first.")

    return watermark[0]["last_processed_order_date"]


def build_dimensions(customers, products, productlines, orders_all):
    dim_customers = (
        customers.select(
            F.col("customerNumber").cast("int").alias("customer_id"),
            F.col("customerName").alias("customer_name"),
            F.concat_ws(" ", F.col("contactFirstName"), F.col("contactLastName")).alias("contact_name"),
            F.col("city").alias("city"),
            F.col("country").alias("country"),
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
            F.col("p.productVendor").alias("product_vendor"),
        )
        .dropDuplicates(["product_id"])
    )

    dim_dates = (
        orders_all.select(F.to_date("orderDate").alias("full_date"))
        .where(F.col("full_date").isNotNull())
        .dropDuplicates(["full_date"])
        .withColumn("date_key", F.date_format(F.col("full_date"), "yyyyMMdd").cast("int"))
        .withColumn("year", F.year("full_date").cast("int"))
        .withColumn("quarter", F.quarter("full_date").cast("int"))
        .withColumn("month", F.month("full_date").cast("int"))
        .withColumn("day", F.dayofmonth("full_date").cast("int"))
        .select("date_key", "full_date", "year", "quarter", "month", "day")
    )

    dim_countries = (
        dim_customers.select("country")
        .where(F.col("country").isNotNull())
        .dropDuplicates(["country"])
        .withColumn("territory", build_country_territory_expr())
        .withColumn("country_key", F.dense_rank().over(Window.orderBy("country")).cast("int"))
        .select("country_key", "country", "territory")
    )

    return dim_customers, dim_products, dim_dates, dim_countries


def build_fact(orderdetails, orders_delta, customers, dim_countries):
    return (
        orderdetails.alias("od")
        .join(orders_delta.alias("o"), F.col("od.orderNumber") == F.col("o.orderNumber"), "inner")
        .join(customers.alias("c"), F.col("o.customerNumber") == F.col("c.customerNumber"), "inner")
        .join(dim_countries.alias("dc"), F.col("c.country") == F.col("dc.country"), "left")
        .select(
            F.col("o.orderNumber").cast("int").alias("order_id"),
            F.col("o.customerNumber").cast("int").alias("customer_id"),
            F.col("od.productCode").alias("product_id"),
            F.date_format(F.to_date(F.col("o.orderDate")), "yyyyMMdd").cast("int").alias("order_date_key"),
            F.col("dc.country_key").cast("int").alias("country_key"),
            F.col("od.quantityOrdered").cast("int").alias("quantity_ordered"),
            F.col("od.priceEach").cast("double").alias("price_each"),
            F.to_date(F.col("o.orderDate")).alias("_order_date"),
        )
        .withColumn("sales_amount", (F.col("quantity_ordered") * F.col("price_each")).cast("double"))
        .withColumn("order_year", F.year("_order_date").cast("int"))
        .withColumn("order_month", F.month("_order_date").cast("int"))
        .drop("_order_date")
    )


def read_existing_affected_partitions(spark, fact_path, affected_partitions):
    frames = []
    for row in affected_partitions:
        path = f"{fact_path}/order_year={row['order_year']}/order_month={row['order_month']}"
        try:
            frame = (
                spark.read.parquet(path)
                .withColumn("order_year", F.lit(row["order_year"]).cast("int"))
                .withColumn("order_month", F.lit(row["order_month"]).cast("int"))
            )
            frames.append(frame)
        except Exception as exc:
            message = str(exc)
            if "Path does not exist" not in message and "FileNotFoundException" not in message:
                raise

    if not frames:
        return None

    existing = frames[0]
    for frame in frames[1:]:
        existing = existing.unionByName(frame)
    return existing


def merge_fact_partitions(spark, fact_delta, output_path):
    fact_path = f"{output_path}/fact_orders"
    affected_partitions = fact_delta.select("order_year", "order_month").dropDuplicates().collect()
    existing = read_existing_affected_partitions(spark, fact_path, affected_partitions)

    if existing is None:
        merged = fact_delta
    else:
        delta_keys = fact_delta.select("order_id", "product_id").dropDuplicates()
        existing_without_delta_keys = existing.join(delta_keys, ["order_id", "product_id"], "left_anti")
        merged = existing_without_delta_keys.unionByName(fact_delta.select(existing_without_delta_keys.columns))

    merged = merged.localCheckpoint(eager=True)
    spark.conf.set("spark.sql.sources.partitionOverwriteMode", "dynamic")
    (
        merged.write.mode("overwrite")
        .partitionBy("order_year", "order_month")
        .parquet(fact_path)
    )


def main():
    args = getResolvedOptions(
        sys.argv,
        [
            "db_name",
            "rds_host",
            "rds_port",
            "rds_user",
            "rds_password",
            "output_path",
        ],
    )

    spark = SparkSession.builder.appName("classicmodels-incremental-etl").getOrCreate()
    jdbc_url = f"jdbc:mysql://{args['rds_host']}:{args['rds_port']}/{args['db_name']}"
    jdbc_props = {
        "user": args["rds_user"],
        "password": args["rds_password"],
        "driver": "com.mysql.cj.jdbc.Driver",
    }

    try:
        last_processed_order_date = read_watermark(spark, jdbc_url, jdbc_props)
        print(f"Watermark atual: {last_processed_order_date}")

        orders_delta = jdbc_table(
            spark,
            jdbc_url,
            jdbc_props,
            f"""(
                SELECT *
                FROM orders
                WHERE orderDate > DATE('{last_processed_order_date}')
            ) orders_delta""",
        )

        delta_orders_count = orders_delta.count()
        if delta_orders_count == 0:
            print("Sem pedidos novos acima do watermark. Nenhuma escrita realizada.")
            update_watermark_no_delta_success(spark, jdbc_url, jdbc_props)
            return

        customers = jdbc_table(spark, jdbc_url, jdbc_props, "customers")
        products = jdbc_table(spark, jdbc_url, jdbc_props, "products")
        productlines = jdbc_table(spark, jdbc_url, jdbc_props, "productlines")
        orders_all = jdbc_table(spark, jdbc_url, jdbc_props, "orders")
        orderdetails = jdbc_table(
            spark,
            jdbc_url,
            jdbc_props,
            f"""(
                SELECT od.*
                FROM orderdetails od
                INNER JOIN orders o ON o.orderNumber = od.orderNumber
                WHERE o.orderDate > DATE('{last_processed_order_date}')
            ) orderdetails_delta""",
        )

        dim_customers, dim_products, dim_dates, dim_countries = build_dimensions(
            customers, products, productlines, orders_all
        )
        fact_delta = build_fact(orderdetails, orders_delta, customers, dim_countries)

        fact_count = fact_delta.count()
        if fact_count == 0:
            raise RuntimeError("Quality gate failed: fact_orders delta has zero rows.")

        invalid_sales_amount = (
            fact_delta.where(
                F.abs(F.col("sales_amount") - (F.col("quantity_ordered") * F.col("price_each"))) > F.lit(0.0001)
            ).count()
        )
        if invalid_sales_amount > 0:
            raise RuntimeError(f"Quality gate failed: invalid_sales_amount={invalid_sales_amount}")

        output_path = args["output_path"].rstrip("/")
        dim_customers.write.mode("overwrite").parquet(f"{output_path}/dim_customers")
        dim_products.write.mode("overwrite").parquet(f"{output_path}/dim_products")
        dim_dates.write.mode("overwrite").parquet(f"{output_path}/dim_dates")
        dim_countries.write.mode("overwrite").parquet(f"{output_path}/dim_countries")
        merge_fact_partitions(spark, fact_delta, output_path)

        max_order_date = orders_delta.select(F.max(F.to_date("orderDate")).alias("max_order_date")).collect()[0][
            "max_order_date"
        ]
        update_watermark_success(spark, jdbc_url, jdbc_props, max_order_date)

        print("ETL incremental concluido.")
        print(f"- pedidos_delta: {delta_orders_count}")
        print(f"- linhas_fact_delta: {fact_count}")
        print(f"- novo_watermark: {max_order_date}")
    except Exception:
        try:
            update_watermark_failure(spark, jdbc_url, jdbc_props)
        except Exception as watermark_error:
            print(f"Falha ao marcar watermark como FAILED: {watermark_error}")
        raise
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
