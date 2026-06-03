import sys
from pyspark.sql import SparkSession, functions as F
from awsglue.utils import getResolvedOptions


def build_country_territory_expr():
    # Mapeamento simples de país para território analítico.
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

    spark = SparkSession.builder.appName("classicmodels-star-schema").getOrCreate()
    # Extração JDBC a partir do RDS MySQL.
    jdbc_url = f"jdbc:mysql://{args['rds_host']}:{args['rds_port']}/{args['db_name']}"
    jdbc_props = {
        "user": args["rds_user"],
        "password": args["rds_password"],
        "driver": "com.mysql.cj.jdbc.Driver",
    }

    customers = spark.read.jdbc(jdbc_url, "customers", properties=jdbc_props)
    products = spark.read.jdbc(jdbc_url, "products", properties=jdbc_props)
    orders = spark.read.jdbc(jdbc_url, "orders", properties=jdbc_props)
    orderdetails = spark.read.jdbc(jdbc_url, "orderdetails", properties=jdbc_props)
    productlines = spark.read.jdbc(jdbc_url, "productlines", properties=jdbc_props)

    dim_customers = (
        # Dimensão de clientes com padronização dos nomes de coluna exigidos.
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
        # Dimensão de produtos com atributos de linha e fornecedor.
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
        # Dimensão de datas derivada da data do pedido.
        orders.select(F.to_date("orderDate").alias("full_date"))
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
        # Dimensão de países com chave surrogate (country_key).
        dim_customers.select("country")
        .where(F.col("country").isNotNull())
        .dropDuplicates(["country"])
        .withColumn("territory", build_country_territory_expr())
        .withColumn("country_key", F.dense_rank().over(Window.orderBy("country")).cast("int"))
        .select("country_key", "country", "territory")
    )

    fact_orders_base = (
        orderdetails.alias("od")
        .join(orders.alias("o"), F.col("od.orderNumber") == F.col("o.orderNumber"), "inner")
        .join(customers.alias("c"), F.col("o.customerNumber") == F.col("c.customerNumber"), "inner")
    )

    fact_orders = (
        # Fato de pedidos com métricas de negócio.
        fact_orders_base.join(dim_countries.alias("dc"), F.col("c.country") == F.col("dc.country"), "left")
        .select(
            F.col("o.orderNumber").cast("int").alias("order_id"),
            F.col("o.customerNumber").cast("int").alias("customer_id"),
            F.col("od.productCode").alias("product_id"),
            F.date_format(F.to_date(F.col("o.orderDate")), "yyyyMMdd").cast("int").alias("order_date_key"),
            F.col("dc.country_key").cast("int").alias("country_key"),
            F.col("od.quantityOrdered").cast("int").alias("quantity_ordered"),
            F.col("od.priceEach").cast("double").alias("price_each"),
        )
        .withColumn("sales_amount", (F.col("quantity_ordered") * F.col("price_each")).cast("double"))
    )

    # Quality gates obrigatórios da tarefa.
    fact_count = fact_orders.count()
    if fact_count == 0:
        raise RuntimeError("Quality gate failed: fact_orders has zero rows.")

    missing_customer_keys = (
        fact_orders.alias("f")
        .join(dim_customers.alias("d"), F.col("f.customer_id") == F.col("d.customer_id"), "left_anti")
        .count()
    )
    missing_product_keys = (
        fact_orders.alias("f")
        .join(dim_products.alias("d"), F.col("f.product_id") == F.col("d.product_id"), "left_anti")
        .count()
    )
    missing_date_keys = (
        fact_orders.alias("f")
        .join(dim_dates.alias("d"), F.col("f.order_date_key") == F.col("d.date_key"), "left_anti")
        .count()
    )
    missing_country_keys = (
        fact_orders.alias("f")
        .join(dim_countries.alias("d"), F.col("f.country_key") == F.col("d.country_key"), "left_anti")
        .count()
    )

    invalid_sales_amount = (
        fact_orders.where(F.abs(F.col("sales_amount") - (F.col("quantity_ordered") * F.col("price_each"))) > F.lit(0.0001))
        .count()
    )

    if any(
        [
            missing_customer_keys > 0,
            missing_product_keys > 0,
            missing_date_keys > 0,
            missing_country_keys > 0,
            invalid_sales_amount > 0,
        ]
    ):
        raise RuntimeError(
            "Quality gate failed: "
            f"missing_customer_keys={missing_customer_keys}, "
            f"missing_product_keys={missing_product_keys}, "
            f"missing_date_keys={missing_date_keys}, "
            f"missing_country_keys={missing_country_keys}, "
            f"invalid_sales_amount={invalid_sales_amount}"
        )

    output_path = args["output_path"].rstrip("/")
    # Load final em Parquet, uma pasta por entidade.
    dim_customers.write.mode("overwrite").parquet(f"{output_path}/dim_customers")
    dim_products.write.mode("overwrite").parquet(f"{output_path}/dim_products")
    dim_dates.write.mode("overwrite").parquet(f"{output_path}/dim_dates")
    dim_countries.write.mode("overwrite").parquet(f"{output_path}/dim_countries")
    fact_orders.write.mode("overwrite").parquet(f"{output_path}/fact_orders")

    spark.stop()


if __name__ == "__main__":
    from pyspark.sql.window import Window

    main()
