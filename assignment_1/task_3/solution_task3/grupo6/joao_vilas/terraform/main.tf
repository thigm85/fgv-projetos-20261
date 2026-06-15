provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project = "classicmodels-task3"
      Owner   = var.owner_tag
      Stack   = "task3-athena-dashboard"
    }
  }
}

locals {
  account_id = data.aws_caller_identity.current.account_id
  partition  = data.aws_partition.current.partition

  etl_bucket_name     = "${var.project_prefix}-etl-${local.account_id}-${var.aws_region}"
  athena_bucket_name  = "${var.project_prefix}-athena-${local.account_id}-${var.aws_region}"
  notebook_bucket_key = "notebooks/classicmodels_dashboard.ipynb"

  glue_script_key = "glue-scripts/etl_classicmodels_star_schema.py"
  output_prefix   = "curated/classicmodels"

  fact_tables = {
    fact_orders = {
      columns = [
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
    dim_customers = {
      columns = [
        { name = "customer_id", type = "int" },
        { name = "customer_name", type = "string" },
        { name = "contact_name", type = "string" },
        { name = "city", type = "string" },
        { name = "country", type = "string" },
      ]
    }
    dim_products = {
      columns = [
        { name = "product_id", type = "string" },
        { name = "product_name", type = "string" },
        { name = "product_line", type = "string" },
        { name = "product_vendor", type = "string" },
      ]
    }
    dim_dates = {
      columns = [
        { name = "date_key", type = "int" },
        { name = "full_date", type = "date" },
        { name = "year", type = "int" },
        { name = "quarter", type = "int" },
        { name = "month", type = "int" },
        { name = "day", type = "int" },
      ]
    }
    dim_countries = {
      columns = [
        { name = "country_key", type = "int" },
        { name = "country", type = "string" },
        { name = "territory", type = "string" },
      ]
    }
  }

  lab_role_arn = data.aws_iam_role.lab_role.arn
}
