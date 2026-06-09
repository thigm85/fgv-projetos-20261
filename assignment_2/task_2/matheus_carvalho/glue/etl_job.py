import sys
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from awsglue.context import GlueContext
from pyspark.sql import DataFrame
from pyspark.sql import functions as F

PIPELINE_NAME = "classicmodels_sales"


def read_table(glue_context: GlueContext, jdbc_url: str, dbtable: str, user: str, password: str) -> DataFrame:
    return (
        glue_context.spark_session.read.format("jdbc")
        .option("url", jdbc_url)
        .option("dbtable", dbtable)
        .option("user", user)
        .option("password", password)
        .option("driver", "com.mysql.cj.jdbc.Driver")
        .load()
    )


def write_parquet(df: DataFrame, bucket: str, prefix: str, table_name: str) -> None:
    output_path = f"s3://{bucket}/{prefix}/{table_name}/"
    df.write.mode("overwrite").parquet(output_path)


def require_non_empty(df: DataFrame, table_name: str) -> None:
    if df.limit(1).count() == 0:
        raise RuntimeError(f"{table_name} is empty")


def ensure_no_orphans(fact_df: DataFrame, dim_customers: DataFrame, dim_products: DataFrame, dim_dates: DataFrame, dim_countries: DataFrame) -> None:
    customer_orphans = (
        fact_df.join(F.broadcast(dim_customers.select("customer_id")), on="customer_id", how="left_anti").count()
    )
    product_orphans = (
        fact_df.join(F.broadcast(dim_products.select("product_id")), on="product_id", how="left_anti").count()
    )
    date_orphans = (
        fact_df.join(F.broadcast(dim_dates.select("date_key")), fact_df.order_date_key == dim_dates.date_key, "left_anti").count()
    )
    country_orphans = (
        fact_df.join(F.broadcast(dim_countries.select("country_key")), on="country_key", how="left_anti").count()
    )

    if any([customer_orphans, product_orphans, date_orphans, country_orphans]):
        raise RuntimeError(
            "Referential integrity validation failed: "
            f"customer_orphans={customer_orphans}, "
            f"product_orphans={product_orphans}, "
            f"date_orphans={date_orphans}, "
            f"country_orphans={country_orphans}"
        )


def ensure_sales_amount(df: DataFrame) -> None:
    invalid_rows = (
        df.filter(
            F.col("sales_amount")
            != F.round(F.col("quantity_ordered").cast("double") * F.col("price_each").cast("double"), 2)
        ).count()
    )
    if invalid_rows > 0:
        raise RuntimeError(f"sales_amount validation failed for {invalid_rows} rows")


def update_watermark(sc: SparkContext, jdbc_url: str, user: str, password: str, pipeline_name: str, new_date_str: str or None, status: str) -> None:
    """Atualiza de forma transacional a tabela etl_watermark via JDBC Java no JVM do Spark."""
    try:
        jvm = sc._jvm
        jvm.java.lang.Class.forName("com.mysql.cj.jdbc.Driver")
        conn = jvm.java.sql.DriverManager.getConnection(jdbc_url, user, password)
        try:
            stmt = conn.createStatement()
            if new_date_str:
                query = f"""
                UPDATE etl_watermark 
                SET last_processed_order_date = '{new_date_str}',
                    last_run_at = NOW(),
                    last_run_status = '{status}'
                WHERE pipeline_name = '{pipeline_name}'
                """
            else:
                query = f"""
                UPDATE etl_watermark 
                SET last_run_at = NOW(),
                    last_run_status = '{status}'
                WHERE pipeline_name = '{pipeline_name}'
                """
            stmt.executeUpdate(query)
            print(f"Watermark atualizado com sucesso. Status: {status}, Data: {new_date_str}")
        finally:
            conn.close()
    except Exception as e:
        print(f"Erro ao atualizar a tabela etl_watermark no RDS: {str(e)}")
        raise


def main():
    args = getResolvedOptions(
        sys.argv,
        [
            "JOB_NAME",
            "db_host",
            "db_port",
            "db_name",
            "db_user",
            "db_password",
            "output_bucket",
            "output_prefix",
        ],
    )

    sc = SparkContext()
    glue_context = GlueContext(sc)
    spark = glue_context.spark_session
    job = Job(glue_context)
    job.init(args["JOB_NAME"], args)

    jdbc_url = f"jdbc:mysql://{args['db_host']}:{args['db_port']}/{args['db_name']}"

    try:
        # ── 1. Leitura do Watermark ───────────────────────────────────────────
        print("Lendo o watermark do banco RDS...")
        watermark_df = read_table(glue_context, jdbc_url, "etl_watermark", args["db_user"], args["db_password"])
        watermark_row = watermark_df.filter(F.col("pipeline_name") == PIPELINE_NAME).collect()
        
        last_processed_date = None
        if watermark_row:
            last_processed_date = watermark_row[0]["last_processed_order_date"]

        if last_processed_date is None:
            # Full load inicial
            last_processed_date_str = "1970-01-01"
            print("Watermark ausente ou NULL. Iniciando carga completa de histórico.")
        else:
            last_processed_date_str = str(last_processed_date)
            print(f"Watermark atual encontrado: {last_processed_date_str}")

        # ── 2. Extração JDBC Filtrada ─────────────────────────────────────────
        orders_all = read_table(glue_context, jdbc_url, "orders", args["db_user"], args["db_password"])
        
        # Filtra os novos pedidos
        orders = orders_all.filter(F.col("orderDate") > last_processed_date_str)
        
        # Verifica se há novos dados a serem processados
        orders_count = orders.limit(1).count()
        if orders_count == 0:
            print("Nenhum pedido novo encontrado após o watermark atual. Finalizando.")
            update_watermark(sc, jdbc_url, args["db_user"], args["db_password"], PIPELINE_NAME, None, "SUCCEEDED")
            job.commit()
            return

        print(f"Pedidos novos encontrados. Iniciando o processamento do delta.")
        orderdetails = read_table(glue_context, jdbc_url, "orderdetails", args["db_user"], args["db_password"])
        customers = read_table(glue_context, jdbc_url, "customers", args["db_user"], args["db_password"])
        products = read_table(glue_context, jdbc_url, "products", args["db_user"], args["db_password"])
        employees = read_table(glue_context, jdbc_url, "employees", args["db_user"], args["db_password"])
        offices = read_table(glue_context, jdbc_url, "offices", args["db_user"], args["db_password"])

        # ── 3. Transformação das Dimensões ────────────────────────────────────
        customer_locations = (
            customers.alias("c")
            .join(
                employees.select(
                    F.col("employeeNumber").alias("employee_number"),
                    F.col("officeCode").alias("office_code"),
                ).alias("e"),
                F.col("c.salesRepEmployeeNumber") == F.col("e.employee_number"),
                "left",
            )
            .join(
                offices.select(
                    F.col("officeCode").alias("office_code"),
                    F.col("territory").alias("territory"),
                ).alias("o"),
                F.col("e.office_code") == F.col("o.office_code"),
                "left",
            )
            .select(
                F.col("c.customerNumber").alias("customer_id"),
                F.col("c.customerName").alias("customer_name"),
                F.concat_ws(" ", F.col("c.contactFirstName"), F.col("c.contactLastName")).alias("contact_name"),
                F.col("c.city").alias("city"),
                F.trim(F.col("c.country")).alias("country"),
                F.coalesce(F.col("o.territory"), F.lit("Unknown")).alias("territory"),
            )
        )

        dim_customers = customer_locations.select(
            "customer_id",
            "customer_name",
            "contact_name",
            "city",
            "country",
        ).dropDuplicates(["customer_id"])

        dim_products = products.select(
            F.col("productCode").alias("product_id"),
            F.col("productName").alias("product_name"),
            F.col("productLine").alias("product_line"),
            F.col("productVendor").alias("product_vendor"),
        ).dropDuplicates(["product_id"])

        # dim_dates gerada a partir do histórico completo para garantir integridade referencial
        dim_dates = (
            orders_all.select(F.col("orderDate").alias("full_date"))
            .dropDuplicates(["full_date"])
            .withColumn("date_key", F.date_format("full_date", "yyyyMMdd").cast("int"))
            .withColumn("year", F.year("full_date"))
            .withColumn("quarter", F.quarter("full_date"))
            .withColumn("month", F.month("full_date"))
            .withColumn("day", F.dayofmonth("full_date"))
            .select("date_key", "full_date", "year", "quarter", "month", "day")
        )

        dim_countries = (
            customer_locations.select("country", "territory")
            .dropDuplicates(["country", "territory"])
            .withColumn("country_key", F.sha2(F.concat_ws("|", F.col("country"), F.col("territory")), 256))
            .select("country_key", "country", "territory")
        )

        # ── 4. Lógica de Fato Incremental e Particionamento ──────────────────
        fact_orders_delta = (
            orders.alias("o")
            .join(orderdetails.alias("od"), F.col("o.orderNumber") == F.col("od.orderNumber"), "inner")
            .join(customer_locations.alias("cl"), F.col("o.customerNumber") == F.col("cl.customer_id"), "inner")
            .select(
                F.col("o.orderNumber").alias("order_id"),
                F.col("o.customerNumber").alias("customer_id"),
                F.col("od.productCode").alias("product_id"),
                F.date_format(F.col("o.orderDate"), "yyyyMMdd").cast("int").alias("order_date_key"),
                F.sha2(F.concat_ws("|", F.col("cl.country"), F.col("cl.territory")), 256).alias("country_key"),
                F.col("od.quantityOrdered").alias("quantity_ordered"),
                F.round(F.col("od.priceEach"), 2).alias("price_each"),
                F.round(F.col("od.quantityOrdered") * F.col("od.priceEach"), 2).alias("sales_amount"),
                # Colunas para chaves de partição
                F.year(F.col("o.orderDate")).cast("int").alias("order_year"),
                F.month(F.col("o.orderDate")).cast("int").alias("order_month"),
            )
        )

        # ── 5. Validações ─────────────────────────────────────────────────────
        require_non_empty(fact_orders_delta, "fact_orders_delta")
        require_non_empty(dim_customers, "dim_customers")
        require_non_empty(dim_products, "dim_products")
        require_non_empty(dim_dates, "dim_dates")
        require_non_empty(dim_countries, "dim_countries")

        ensure_no_orphans(fact_orders_delta, dim_customers, dim_products, dim_dates, dim_countries)
        ensure_sales_amount(fact_orders_delta)

        # ── 6. Merge e Overwrite Dinâmico na Fato ──────────────────────────────
        output_path = f"s3://{args['output_bucket']}/{args['output_prefix']}/fact_orders"
        
        # Identifica as partições que serão tocadas pelo delta
        affected_partitions = fact_orders_delta.select("order_year", "order_month").distinct().collect()

        if affected_partitions:
            try:
                # Tenta ler as partições existentes no S3
                existing_fact = spark.read.parquet(output_path)
                
                # Monta filtro condicional
                filter_cond = None
                for row in affected_partitions:
                    cond = (F.col("order_year") == row["order_year"]) & (F.col("order_month") == row["order_month"])
                    if filter_cond is None:
                        filter_cond = cond
                    else:
                        filter_cond = filter_cond | cond
                
                # Filtra apenas as partições afetadas
                existing_affected = existing_fact.filter(filter_cond)
                
                # Merge dos dados novos com os antigos dessas partições
                merged_fact = existing_affected.unionByName(fact_orders_delta)
                
                # Remove duplicatas baseadas na chave composta da fato
                merged_fact = merged_fact.dropDuplicates(["order_id", "product_id"])
                print(f"Mesclando {fact_orders_delta.count()} registros novos com partições afetadas existentes.")
            except Exception as e:
                print(f"Primeira carga ou estrutura inexistente no S3: {str(e)}")
                merged_fact = fact_orders_delta

            # Habilita overwrite de partição dinâmica (Dynamic Partition Overwrite)
            spark.conf.set("spark.sql.sources.partitionOverwriteMode", "dynamic")
            
            # Grava na Fato mantendo o particionamento Hive
            merged_fact.write.mode("overwrite").partitionBy("order_year", "order_month").parquet(output_path)
            print("Escrita da tabela fato finalizada com sucesso.")

        # ── 7. Overwrite das Dimensões (Opção A) ──────────────────────────────
        write_parquet(dim_customers, args["output_bucket"], args["output_prefix"], "dim_customers")
        write_parquet(dim_products, args["output_bucket"], args["output_prefix"], "dim_products")
        write_parquet(dim_dates, args["output_bucket"], args["output_prefix"], "dim_dates")
        write_parquet(dim_countries, args["output_bucket"], args["output_prefix"], "dim_countries")
        print("Dimensões atualizadas com sucesso (Overwrite completo).")

        # ── 8. Commit do Watermark ────────────────────────────────────────────
        max_date_row = orders.select(F.max("orderDate")).collect()
        new_watermark_date = max_date_row[0][0]
        
        if new_watermark_date:
            new_watermark_str = str(new_watermark_date)
            update_watermark(sc, jdbc_url, args["db_user"], args["db_password"], PIPELINE_NAME, new_watermark_str, "SUCCEEDED")
        else:
            update_watermark(sc, jdbc_url, args["db_user"], args["db_password"], PIPELINE_NAME, None, "SUCCEEDED")

        job.commit()

    except Exception as exc:
        print(f"Falha na execução do Job Glue Incremental: {str(exc)}")
        try:
            update_watermark(sc, jdbc_url, args["db_user"], args["db_password"], PIPELINE_NAME, None, "FAILED")
        except Exception:
            pass
        raise exc


if __name__ == "__main__":
    main()
