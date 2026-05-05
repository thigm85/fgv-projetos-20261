import sys
from awsglue.transforms import *
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from awsglue.context import GlueContext
from awsglue.job import Job
from pyspark.sql import functions as F
from pyspark.sql.window import Window

# Captura argumentos do Glue Job
args = getResolvedOptions(sys.argv, ['JOB_NAME', 'connection_name', 's3_output_path', 'db_name'])

sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)
job.init(args['JOB_NAME'], args)

db_name = args['db_name']
connection_name = args['connection_name']
output_path = args['s3_output_path']

def read_table(table_name):
    return glueContext.create_dynamic_frame.from_options(
        connection_type="mysql",
        connection_options={
            "useConnectionProperties": "true",
            "dbtable": f"{db_name}.{table_name}",
            "connectionName": connection_name,
        }
    ).toDF()

# 1. Extração
print(f"Extraindo tabelas do banco {db_name}...")
customers = read_table("customers")
products = read_table("products")
productlines = read_table("productlines")
orders = read_table("orders")
orderdetails = read_table("orderdetails")
offices = read_table("offices")
employees = read_table("employees")

# 2. Transformação

# Dim Customers
dim_customers = customers.select(
    F.col("customerNumber").alias("customer_id"),
    F.col("customerName").alias("customer_name"),
    F.concat(F.col("contactFirstName"), F.lit(" "), F.col("contactLastName")).alias("contact_name"),
    F.col("city"),
    F.col("country")
).distinct()

# Dim Products
dim_products = products.join(productlines, "productLine").select(
    F.col("productCode").alias("product_id"),
    F.col("productName").alias("product_name"),
    F.col("productLine").alias("product_line"),
    F.col("productVendor").alias("product_vendor")
).distinct()

# Dim Countries 
countries_raw = customers.select("country").union(offices.select("country")).distinct()
territories = offices.select("country", "territory").distinct()
dim_countries_prep = countries_raw.join(territories, "country", "left") \
    .withColumn("territory", F.coalesce(F.col("territory"), F.lit("Unknown")))

window_country = Window.orderBy("country")
dim_countries = dim_countries_prep.filter(F.col("country").isNotNull()).withColumn(
    "country_key", F.row_number().over(window_country)
).select("country_key", "country", "territory")

# Dim Dates (Baseada nas datas de pedidos)
dates_raw = orders.select(F.col("orderDate").alias("full_date")).distinct()
dim_dates = dates_raw.withColumn("date_key", F.date_format(F.col("full_date"), "yyyyMMdd").cast("int")) \
    .withColumn("year", F.year(F.col("full_date"))) \
    .withColumn("quarter", F.quarter(F.col("full_date"))) \
    .withColumn("month", F.month(F.col("full_date"))) \
    .withColumn("day", F.dayofmonth(F.col("full_date")))

# Fact Orders
fact_orders = orders.join(orderdetails, "orderNumber") \
    .join(customers, "customerNumber") \
    .join(dim_countries, customers.country == dim_countries.country, "left") \
    .select(
        F.col("orderNumber").alias("order_id"),
        F.col("customerNumber").alias("customer_id"),
        F.col("productCode").alias("product_id"),
        F.date_format(F.col("orderDate"), "yyyyMMdd").cast("int").alias("order_date_key"),
        F.col("country_key"),
        F.col("quantityOrdered").alias("quantity_ordered"),
        F.col("priceEach").alias("price_each")
    )


fact_orders = fact_orders.withColumn(
    "sales_amount", 
    F.round(F.col("quantity_ordered") * F.col("price_each"), 2)
)

# 3. Carga (Load) para S3 em Parquet
tables_to_load = {
    "fact_orders": fact_orders,
    "dim_customers": dim_customers,
    "dim_products": dim_products,
    "dim_dates": dim_dates,
    "dim_countries": dim_countries
}

for table_name, df in tables_to_load.items():
    target_dir = f"{output_path}/{table_name}"
    print(f"Salvando {table_name} em {target_dir}...")
    df.write.mode("overwrite").parquet(target_dir)

job.commit()
