import sys

from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from pyspark.sql import functions as F
from pyspark.sql.window import Window


def _read_table(glue_ctx: GlueContext, connection_name: str, table: str):
    dyf = glue_ctx.create_dynamic_frame.from_options(
        connection_type="mysql",
        connection_options={
            "connectionName": connection_name,
            "dbtable": table,
        },
        transformation_ctx=f"read_{table}",
    )
    return dyf.toDF()


def main():
    args = getResolvedOptions(
        sys.argv,
        [
            "JOB_NAME",
            "GLUE_CONNECTION_NAME",
            "S3_OUTPUT_BASE",
        ],
    )

    sc = SparkContext.getOrCreate()
    glue_ctx = GlueContext(sc)
    spark = glue_ctx.spark_session
    job = Job(glue_ctx)
    job.init(args["JOB_NAME"], args)

    connection_name = args["GLUE_CONNECTION_NAME"]
    s3_base = args["S3_OUTPUT_BASE"].rstrip("/")

    # Source tables (classicmodels schema)
    orders = _read_table(glue_ctx, connection_name, "orders").select(
        F.col("orderNumber").alias("order_id"),
        F.col("orderDate").alias("order_date"),
        F.col("customerNumber").alias("customer_id"),
    )

    orderdetails = _read_table(glue_ctx, connection_name, "orderdetails").select(
        F.col("orderNumber").alias("order_id"),
        F.col("productCode").alias("product_id"),
        F.col("quantityOrdered").cast("int").alias("quantity_ordered"),
        F.col("priceEach").cast("double").alias("price_each"),
    )

    customers = _read_table(glue_ctx, connection_name, "customers").select(
        F.col("customerNumber").alias("customer_id"),
        F.col("customerName").alias("customer_name"),
        F.concat_ws(" ", F.col("contactFirstName"), F.col("contactLastName")).alias("contact_name"),
        F.col("city").alias("city"),
        F.col("country").alias("country"),
        F.col("salesRepEmployeeNumber").alias("sales_rep_employee_number"),
    )

    products = _read_table(glue_ctx, connection_name, "products").select(
        F.col("productCode").alias("product_id"),
        F.col("productName").alias("product_name"),
        F.col("productLine").alias("product_line"),
        F.col("productVendor").alias("product_vendor"),
    )

    employees = _read_table(glue_ctx, connection_name, "employees").select(
        F.col("employeeNumber").alias("employee_number"),
        F.col("officeCode").alias("office_code"),
    )

    offices = _read_table(glue_ctx, connection_name, "offices").select(
        F.col("officeCode").alias("office_code"),
        F.col("territory").alias("territory"),
    )

    # Dimensions
    dim_customers = customers.select(
        "customer_id",
        "customer_name",
        "contact_name",
        "city",
        "country",
    ).dropDuplicates(["customer_id"])

    dim_products = products.select(
        "product_id",
        "product_name",
        "product_line",
        "product_vendor",
    ).dropDuplicates(["product_id"])

    dim_dates = (
        orders.select(F.to_date("order_date").alias("full_date"))
        .dropDuplicates(["full_date"])
        .withColumn("year", F.year("full_date").cast("int"))
        .withColumn("quarter", F.quarter("full_date").cast("int"))
        .withColumn("month", F.month("full_date").cast("int"))
        .withColumn("day", F.dayofmonth("full_date").cast("int"))
        .withColumn("date_key", F.date_format("full_date", "yyyyMMdd").cast("int"))
        .select("date_key", "full_date", "year", "quarter", "month", "day")
    )

    cust_loc = (
        customers.join(
            employees,
            customers["sales_rep_employee_number"] == employees["employee_number"],
            how="left",
        )
        .join(offices, "office_code", how="left")
        .select(
            customers["customer_id"],
            customers["country"].alias("country"),
            F.coalesce(offices["territory"], F.lit("Unknown")).alias("territory"),
        )
    )

    w = Window.orderBy(F.col("country"), F.col("territory"))
    dim_countries = (
        cust_loc.select("country", "territory")
        .dropDuplicates(["country", "territory"])
        .withColumn("country_key", F.dense_rank().over(w).cast("int"))
        .select("country_key", "country", "territory")
    )

    cust_with_country_key = cust_loc.join(
        dim_countries, on=["country", "territory"], how="left"
    ).select(
        "customer_id",
        "country_key",
    )

    # Fact
    fact_orders = (
        orders.join(orderdetails, "order_id", how="inner")
        .join(customers.select("customer_id", "country"), "customer_id", how="left")
        .join(cust_with_country_key, "customer_id", how="left")
        .withColumn("order_date_key", F.date_format(F.to_date("order_date"), "yyyyMMdd").cast("int"))
        .withColumn("sales_amount", (F.col("quantity_ordered") * F.col("price_each")).cast("double"))
        .select(
            F.col("order_id").cast("int").alias("order_id"),
            F.col("customer_id").cast("int").alias("customer_id"),
            F.col("product_id").alias("product_id"),
            F.col("order_date_key").cast("int").alias("order_date_key"),
            F.col("country_key").cast("int").alias("country_key"),
            F.col("quantity_ordered").cast("int").alias("quantity_ordered"),
            F.col("price_each").cast("double").alias("price_each"),
            F.col("sales_amount").cast("double").alias("sales_amount"),
        )
    )

    # Minimal validation (Task 4.6)
    fact_count = fact_orders.count()
    if fact_count == 0:
        raise RuntimeError("fact_orders está vazio (0 registros).")

    bad_sales = fact_orders.where(
        F.abs(F.col("sales_amount") - (F.col("quantity_ordered") * F.col("price_each"))) > F.lit(1e-9)
    ).count()
    if bad_sales > 0:
        raise RuntimeError(f"sales_amount inconsistente em {bad_sales} registros.")

    # Write Parquet outputs (one folder per table name)
    dim_customers.write.mode("overwrite").parquet(f"{s3_base}/dim_customers")
    dim_products.write.mode("overwrite").parquet(f"{s3_base}/dim_products")
    dim_dates.write.mode("overwrite").parquet(f"{s3_base}/dim_dates")
    dim_countries.write.mode("overwrite").parquet(f"{s3_base}/dim_countries")
    fact_orders.write.mode("overwrite").parquet(f"{s3_base}/fact_orders")

    job.commit()


if __name__ == "__main__":
    main()

