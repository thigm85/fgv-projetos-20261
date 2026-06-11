import sys
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from awsglue.context import GlueContext
from awsglue.job import Job

def extract_table(glue_context, connection_name, table_name):
    """
    Extract a table from the mysql database using glube
    """
    return glue_context.create_dynamic_frame.from_options(
        connection_type="mysql",
        connection_options={
            "useConnectionProperties": "true",
            "dbtable": table_name,
            "connectionName": connection_name,
        }
    )

def main():
    """
    Main function for Job execution
    
    What it does:
    1. Initialize Spark and Glue
    2. Get terraform args
    3. Getting raw data from the MySql db
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

    tables_to_extract = [
        "customers",
        "products",
        "productlines",
        "orders",
        "orderdetails",
        "employees",
        "offices"
    ]

    # Getting the DynamicFrames from Glue
    raw_data = {}
    for table in tables_to_extract:
        raw_data[table] = extract_table(
            glue_context=glueContext,
            connection_name=connection_name,
            table_name=table
        )
        raw_data[table].printSchema()

    print("Começando a extração!")
    # DynamicFrames (Glue) to DataFrames (Spark)
    from pyspark.sql import functions as F
    df_customers = raw_data["customers"].toDF()
    df_products = raw_data["products"].toDF()
    df_orders = raw_data["orders"].toDF()
    df_orderdetails = raw_data["orderdetails"].toDF()
    df_employees = raw_data["employees"].toDF()
    df_offices = raw_data["offices"].toDF()

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

    # 6. fact_orders: mkaing the join between the customer and the order number
    df_fact_base = df_orders.join(df_orderdetails, "orderNumber", "inner") \
                            .join(df_customers, "customerNumber", "inner")

    fact_orders = df_fact_base.select(
        F.col("orderNumber").alias("order_id"),
        F.col("customerNumber").alias("customer_id"),
        F.col("productCode").alias("product_id"),
        F.date_format(F.col("orderDate"), "yyyyMMdd").cast("int").alias("order_date_key"),
        F.md5(F.col("country")).alias("country_key"),
        F.col("quantityOrdered").alias("quantity_ordered"),
        F.col("priceEach").alias("price_each"),
        (F.col("quantityOrdered") * F.col("priceEach")).alias("sales_amount")
    )

    transformed_data = {
        "dim_customers": dim_customers,
        "dim_products": dim_products,
        "dim_dates": dim_dates,
        "dim_countries": dim_countries,
        "fact_orders": fact_orders
    }

    # =========================================================================
    # LOAD
    # =========================================================================
    print("Iniciando a carga de dados (Load) no S3!!!")

    for table_name, df in transformed_data.items():
        output_path = f"{target_bucket}{table_name}/"
        print(f"Gravando a tabela '{table_name}' em: {output_path}")

        # Save into the parquet
        df.write \
            .mode("overwrite") \
            .parquet(output_path)

    print("Processo ETL finalizado com sucesso!")
    job.commit()

if __name__ == '__main__':
    main()