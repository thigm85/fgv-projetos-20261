provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project = "classicmodels-a2-task2"
      Owner   = var.owner_tag
      Stack   = "a2-task2-incremental-etl"
    }
  }
}

locals {
  account_id = data.aws_caller_identity.current.account_id
  partition  = data.aws_partition.current.partition

  etl_bucket_name = "${var.project_prefix}-etl-${local.account_id}-${var.aws_region}"

  glue_script_key  = "glue-scripts/etl_classicmodels_incremental.py"
  analytics_prefix = "analytics"
  fact_s3_location = "s3://${aws_s3_bucket.etl_bucket.bucket}/${local.analytics_prefix}/fact_orders"

  lab_role_arn = data.aws_iam_role.lab_role.arn

  year_range  = split(",", var.partition_year_range)
  month_range = "1,12"

  # Dimensões (sem partição): overwrite completo a cada run (Opção A do brief).
  dim_tables = {
    dim_customers = [
      { name = "customer_id", type = "int" },
      { name = "customer_name", type = "string" },
      { name = "contact_name", type = "string" },
      { name = "city", type = "string" },
      { name = "country", type = "string" },
    ]
    dim_products = [
      { name = "product_id", type = "string" },
      { name = "product_name", type = "string" },
      { name = "product_line", type = "string" },
      { name = "product_vendor", type = "string" },
    ]
    dim_dates = [
      { name = "date_key", type = "int" },
      { name = "full_date", type = "date" },
      { name = "year", type = "int" },
      { name = "quarter", type = "int" },
      { name = "month", type = "int" },
      { name = "day", type = "int" },
    ]
    dim_countries = [
      { name = "country_key", type = "int" },
      { name = "country", type = "string" },
      { name = "territory", type = "string" },
    ]
  }

  # Colunas NÃO-partição de fact_orders (order_year/order_month são partition keys).
  fact_columns = [
    { name = "order_id", type = "int" },
    { name = "customer_id", type = "int" },
    { name = "product_id", type = "string" },
    { name = "order_date_key", type = "int" },
    { name = "country_key", type = "int" },
    { name = "quantity_ordered", type = "int" },
    { name = "price_each", type = "decimal(10,2)" },
    { name = "sales_amount", type = "decimal(18,2)" },
  ]
}
