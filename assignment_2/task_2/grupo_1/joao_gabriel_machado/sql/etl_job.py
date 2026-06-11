import sys
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from awsglue.context import GlueContext
from awsglue.job import Job
from pyspark.sql import functions as F

def extract_table(glue_context, connection_name, table_name, custom_query=None):
    """
    Extract a table or query from the mysql database using glue
    """
    options = {
        "useConnectionProperties": "true",
        "connectionName": connection_name,
        "dbtable": table_name,
    }
    
    # If a custom query is passed (for incremental load), use sampleQuery
    if custom_query:
        options["sampleQuery"] = custom_query
    else:
        options["dbtable"] = table_name

    return glue_context.create_dynamic_frame.from_options(
        connection_type="mysql",
        connection_options=options
    )

def execute_raw_sql(sc, jdbc_url, user, password, query):
    """
    Helper function to execute raw SQL (like UPDATE) directly via PySpark's JVM.
    """
    conn = sc._gateway.jvm.java.sql.DriverManager.getConnection(jdbc_url, user, password)
    stmt = conn.createStatement()
    stmt.executeUpdate(query)
    stmt.close()
    conn.close()

def main():
    """
    Main function for Job execution
    
    What it does:
    1. Initialize Spark and Glue
    2. Get terraform args
    3. Getting raw data from the MySql db (INCREMENTAL)
    4. Transform data into Star Schema
    5. Load to S3 and Update Watermark
    """
    args = getResolvedOptions(sys.argv, ['JOB_NAME', 'target_bucket'])
    
    # Contexts and arguments for job
    sc = SparkContext()
    glueContext = GlueContext(sc)
    spark = glueContext.spark_session
    job = Job(glueContext)
    job.init(args['JOB_NAME'], args)
    
    target_bucket = args['target_bucket']
    connection_name = "classicmodels-rds-conn"

    # =========================================================================
    # READ WATERMARK
    # =========================================================================
    print("Reading Watermark from RDS...")
    jdbc_conf = glueContext.extract_jdbc_conf(connection_name)
    jdbc_url = jdbc_conf['url']
    db_user = jdbc_conf['user']
    db_pass = jdbc_conf['password']

    watermark_query = "(SELECT last_processed_order_date FROM classicmodels.etl_watermark WHERE pipeline_name = 'classicmodels_sales') as wm"
    df_watermark = spark.read.format("jdbc") \
        .option("url", jdbc_url).option("dbtable", watermark_query) \
        .option("user", db_user).option("password", db_pass).load()
    
    watermark_row = df_watermark.collect()
    
    # Handling initialization or NEVER_RUN
    if watermark_row and watermark_row[0][0] is not None:
        last_date = watermark_row[0][0].strftime("%Y-%m-%d")
    else:
        last_date = "1900-01-01" 
        
    print(f"Incremental Extraction Threshold: orderDate > {last_date}")

    try:
        # =========================================================================
        # INCREMENTAL EXTRACTION
        # =========================================================================
        tables_to_extract = ["customers", "products", "productlines", "orderdetails", "employees", "offices"]
        raw_data = {}
        
        # Extract full dimensions
        for table in tables_to_extract:
            raw_data[table] = extract_table(glueContext, connection_name, table)
        
        # Extract delta orders (Pushdown Predicate)
        incremental_sql = f"SELECT * FROM orders WHERE orderDate > '{last_date}'"
        raw_data["orders"] = extract_table(glueContext, connection_name, "orders", custom_query=incremental_sql)

        print("Começando a transformação!")
        df_customers = raw_data["customers"].toDF()
        df_products = raw_data["products"].toDF()
        df_orders = raw_data["orders"].toDF()
        df_orderdetails = raw_data["orderdetails"].toDF()
        df_employees = raw_data["employees"].toDF()
        df_offices = raw_data["offices"].toDF()

        # Check if there are new orders. If not, we skip the heavy processing.
        if df_orders.isEmpty():
            print("No new orders found. Exiting gracefully.")
            job.commit()
            return

        # Get the new watermark date from the fetched delta
        new_max_date_row = df_orders.select(F.max("orderDate")).collect()
        new_max_date = new_max_date_row[0][0].strftime("%Y-%m-%d")

        # 2. dim_customers
        dim_customers = df_customers.select(
            F.col("customerNumber").alias("customer_id"),
            F.col("customerName").alias("customer_name"),
            F.concat_ws(" ", F.col("contactFirstName"), F.col("contactLastName")).alias("contact_name"),
            F.col("city"),
            F.col("country")
        )

        # 3. dim_products
        dim_products = df_products.select(
            F.col("productCode").alias("product_id"),
            F.col("productName").alias("product_name"),
            F.col("productLine").alias("product_line"),
            F.col("productVendor").alias("product_vendor")
        )

        # 4. dim_dates
        dim_dates = df_orders.select(F.col("orderDate").alias("full_date")).distinct()
        dim_dates = dim_dates.select(
            F.date_format(F.col("full_date"), "yyyyMMdd").cast("int").alias("date_key"),
            F.col("full_date"),
            F.year(F.col("full_date")).alias("year"),
            F.quarter(F.col("full_date")).alias("quarter"),
            F.month(F.col("full_date")).alias("month"),
            F.dayofmonth(F.col("full_date")).alias("day")
        )

        # 5. dim_countries
        df_cust_emp = df_customers.join(
            df_employees, 
            df_customers.salesRepEmployeeNumber == df_employees.employeeNumber, 
            "left"
        )
        df_cust_off = df_cust_emp.join(
            df_offices, 
            df_cust_emp.officeCode == df_offices.officeCode, 
            "left"
        )

        dim_countries = df_cust_off.select(
            df_customers["country"],
            F.coalesce(F.col("territory"), F.lit("Unknown")).alias("territory")
        ).distinct()

        dim_countries = dim_countries.withColumn("country_key", F.md5(F.col("country")))
        dim_countries = dim_countries.select("country_key", "country", "territory")

        # 6. fact_orders
        df_fact_base = df_orders.join(df_orderdetails, "orderNumber", "inner") \
                                .join(df_customers, "customerNumber", "inner")

        # =========================================================================
        # ADD PARTITION COLUMNS
        # =========================================================================
        fact_orders = df_fact_base.select(
            F.col("orderNumber").alias("order_id"),
            F.col("customerNumber").alias("customer_id"),
            F.col("productCode").alias("product_id"),
            F.date_format(F.col("orderDate"), "yyyyMMdd").cast("int").alias("order_date_key"),
            F.md5(F.col("country")).alias("country_key"),
            F.col("quantityOrdered").alias("quantity_ordered"),
            F.col("priceEach").alias("price_each"),
            (F.col("quantityOrdered") * F.col("priceEach")).alias("sales_amount"),
            F.year(F.col("orderDate")).alias("order_year"),    # New partition key
            F.month(F.col("orderDate")).alias("order_month")   # New partition key
        )

        transformed_data = {
            "dim_customers": dim_customers,
            "dim_products": dim_products,
            "dim_dates": dim_dates,
            "dim_countries": dim_countries,
            "fact_orders": fact_orders
        }

        # =========================================================================
        # LOAD WITH PARTITIONS
        # =========================================================================
        print("Iniciando a carga de dados (Load) no S3!!!")

        for table_name, df in transformed_data.items():
            output_path = f"{target_bucket}{table_name}/"
            print(f"Gravando a tabela '{table_name}' em: {output_path}")

            if table_name == "fact_orders":
                # Fact is appended and partitioned
                df.write.mode("append").partitionBy("order_year", "order_month").parquet(output_path)
            else:
                # Dimensions are fully overwritten
                df.write.mode("overwrite").parquet(output_path)

        # =========================================================================
        # UPDATE WATERMARK (SUCCEEDED)
        # =========================================================================
        print(f"Updating watermark to new max date: {new_max_date}")
        success_sql = f"""
            UPDATE classicmodels.etl_watermark 
            SET last_processed_order_date = '{new_max_date}', 
                last_run_at = UTC_TIMESTAMP(), 
                last_run_status = 'SUCCEEDED' 
            WHERE pipeline_name = 'classicmodels_sales'
        """
        execute_raw_sql(sc, jdbc_url, db_user, db_pass, success_sql)
        print("Processo ETL Incremental finalizado com sucesso!")
        
        job.commit()

    except Exception as e:
        # =========================================================================
        # UPDATE WATERMARK (FAILED)
        # =========================================================================
        print(f"ETL Job Failed! Rolling back watermark status. Error: {str(e)}")
        fail_sql = """
            UPDATE classicmodels.etl_watermark 
            SET last_run_status = 'FAILED',
                last_run_at = UTC_TIMESTAMP()
            WHERE pipeline_name = 'classicmodels_sales'
        """

if __name__ == '__main__':
    main()