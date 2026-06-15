"""SQL e configuração do Glue/Athena (esquema estrela da Task 2)."""

# Mesma região do Terraform (task_2_redo): variable aws_region default us-east-1
AWS_REGION = "us-east-1"

# Substitua pelo output: terraform output -raw glue_database_name
GLUE_DATABASE = "classicmodels_star_g4"


SQL_DIM_PRODUCTS = """
SELECT
    product_id,
    product_name,
    product_line,
    product_vendor
FROM dim_products
LIMIT 20
"""


SQL_SALES_BY_COUNTRY = """
SELECT
    dim_countries.country,
    SUM(fact_orders.sales_amount) AS total_sales
FROM fact_orders
JOIN dim_countries ON fact_orders.country_key = dim_countries.country_key
GROUP BY dim_countries.country
ORDER BY total_sales DESC
LIMIT 10
"""


SQL_SALES_DETAIL = """
SELECT
    dim_dates.full_date,
    dim_products.product_line,
    dim_products.product_name,
    dim_countries.country,
    SUM(fact_orders.sales_amount) AS total_sales
FROM fact_orders
JOIN dim_products ON fact_orders.product_id = dim_products.product_id
JOIN dim_countries ON fact_orders.country_key = dim_countries.country_key
JOIN dim_dates ON fact_orders.order_date_key = dim_dates.date_key
GROUP BY
    dim_dates.full_date,
    dim_products.product_line,
    dim_products.product_name,
    dim_countries.country
"""
