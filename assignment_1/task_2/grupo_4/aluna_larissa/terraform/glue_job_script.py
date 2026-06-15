import sys

from awsglue.context import GlueContext
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from pyspark.sql import functions as F


def _read_mysql_table(*, spark, url: str, user: str, password: str, table: str):
    return (
        spark.read.format("jdbc")
        .option("url", url)
        .option("dbtable", table)
        .option("user", user)
        .option("password", password)
        .option("driver", "com.mysql.cj.jdbc.Driver")
        .load()
    )


def main():
    args = getResolvedOptions(
        sys.argv,
        [
            "JOB_NAME",
            "rds_endpoint",
            "rds_port",
            "db_name",
            "db_user",
            "db_password",
            "s3_bucket",
            "out_prefix",
        ],
    )

    sc = SparkContext.getOrCreate()
    glue_context = GlueContext(sc)
    spark = glue_context.spark_session

    rds_endpoint = args["rds_endpoint"]
    rds_port = args["rds_port"]
    db_name = args["db_name"]
    db_user = args["db_user"]
    db_password = args["db_password"]
    s3_bucket = args["s3_bucket"]
    out_prefix = args["out_prefix"].strip("/")

    jdbc_url = f"jdbc:mysql://{rds_endpoint}:{rds_port}/{db_name}"

    # Source tables (minimum needed for star schema)
    orders = _read_mysql_table(spark=spark, url=jdbc_url, user=db_user, password=db_password, table="orders")
    orderdetails = _read_mysql_table(
        spark=spark, url=jdbc_url, user=db_user, password=db_password, table="orderdetails"
    )
    customers = _read_mysql_table(spark=spark, url=jdbc_url, user=db_user, password=db_password, table="customers")
    products = _read_mysql_table(spark=spark, url=jdbc_url, user=db_user, password=db_password, table="products")
    productlines = _read_mysql_table(
        spark=spark, url=jdbc_url, user=db_user, password=db_password, table="productlines"
    )
    employees = _read_mysql_table(spark=spark, url=jdbc_url, user=db_user, password=db_password, table="employees")
    offices = _read_mysql_table(spark=spark, url=jdbc_url, user=db_user, password=db_password, table="offices")

    # --- Dimensions ---
    dim_customers = (
        customers.select(
            F.col("customerNumber").cast("int").alias("customer_id"),
            F.col("customerName").cast("string").alias("customer_name"),
            F.concat_ws(" ", F.col("contactFirstName"), F.col("contactLastName")).cast("string").alias("contact_name"),
            F.col("city").cast("string").alias("city"),
            F.col("country").cast("string").alias("country"),
        )
        .dropna(subset=["customer_id"])
        .dropDuplicates(["customer_id"])
    )

    dim_products = (
        products.join(productlines, on="productLine", how="left")
        .select(
            F.col("productCode").cast("string").alias("product_id"),
            F.col("productName").cast("string").alias("product_name"),
            F.col("productLine").cast("string").alias("product_line"),
            F.col("productVendor").cast("string").alias("product_vendor"),
        )
        .dropna(subset=["product_id"])
        .dropDuplicates(["product_id"])
    )

    # Countries dimension: classicmodels has territory in `offices`, not in `customers`.
    # Derive customer territory via customers.salesRepEmployeeNumber -> employees.officeCode -> offices.territory
    cust_with_territory = (
        customers.select(
            F.col("customerNumber").cast("int").alias("customer_id"),
            F.col("country").cast("string").alias("country"),
            F.col("salesRepEmployeeNumber").cast("int").alias("sales_rep_employee_number"),
        )
        .join(
            employees.select(
                F.col("employeeNumber").cast("int").alias("employee_number"),
                F.col("officeCode").cast("string").alias("office_code"),
            ),
            on=F.col("sales_rep_employee_number") == F.col("employee_number"),
            how="left",
        )
        .join(
            offices.select(
                F.col("officeCode").cast("string").alias("office_code_office"),
                F.col("territory").cast("string").alias("territory"),
            ),
            on=F.col("office_code") == F.col("office_code_office"),
            how="left",
        )
        .select("customer_id", "country", "territory")
    )

    dim_countries = (
        cust_with_territory.select("country", "territory")
        .dropna(subset=["country"])
        .dropDuplicates(["country", "territory"])
        .withColumn("country_key", F.xxhash64(F.col("country")).cast("long"))
        .select("country_key", "country", "territory")
        .dropDuplicates(["country_key"])
    )

    # Dates dimension from orders.orderDate
    order_dates = orders.select(F.to_date(F.col("orderDate")).alias("full_date")).dropna()
    dim_dates = (
        order_dates.dropDuplicates(["full_date"])
        .withColumn("year", F.year("full_date").cast("int"))
        .withColumn("quarter", F.quarter("full_date").cast("int"))
        .withColumn("month", F.month("full_date").cast("int"))
        .withColumn("day", F.dayofmonth("full_date").cast("int"))
        .withColumn("date_key", F.date_format("full_date", "yyyyMMdd").cast("int"))
        .select("date_key", "full_date", "year", "quarter", "month", "day")
        .dropDuplicates(["date_key"])
    )

    # --- Fact table ---
    fact_orders_base = (
        orderdetails.join(orders, on="orderNumber", how="inner")
        .join(customers.select("customerNumber", "country"), on="customerNumber", how="left")
        .select(
            F.col("orderNumber").cast("int").alias("order_id"),
            F.col("customerNumber").cast("int").alias("customer_id"),
            F.col("productCode").cast("string").alias("product_id"),
            F.to_date(F.col("orderDate")).alias("order_date"),
            F.col("country").cast("string").alias("country"),
            F.col("quantityOrdered").cast("int").alias("quantity_ordered"),
            F.col("priceEach").cast("double").alias("price_each"),
        )
    )

    fact_orders = (
        fact_orders_base.withColumn("order_date_key", F.date_format("order_date", "yyyyMMdd").cast("int"))
        .withColumn("country_key", F.xxhash64(F.col("country")).cast("long"))
        .withColumn("sales_amount", (F.col("quantity_ordered") * F.col("price_each")).cast("double"))
        .select(
            "order_id",
            "customer_id",
            "product_id",
            "order_date_key",
            "country_key",
            "quantity_ordered",
            "price_each",
            "sales_amount",
        )
    )

    # --- Write outputs ---
    base_path = f"s3://{s3_bucket}/{out_prefix}"

    def _write_parquet(df, name: str):
        (
            df.repartition(1)
            .write.mode("overwrite")
            .parquet(f"{base_path}/{name}/")
        )

    _write_parquet(dim_customers, "dim_customers")
    _write_parquet(dim_products, "dim_products")
    _write_parquet(dim_dates, "dim_dates")
    _write_parquet(dim_countries, "dim_countries")
    _write_parquet(fact_orders, "fact_orders")


if __name__ == "__main__":
    main()

