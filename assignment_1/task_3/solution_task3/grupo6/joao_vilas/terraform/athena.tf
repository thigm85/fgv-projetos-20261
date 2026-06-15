resource "aws_athena_workgroup" "task3" {
  name        = "${var.project_prefix}-wg"
  description = "Workgroup do Athena para o dashboard da Task 3"
  state       = "ENABLED"

  configuration {
    enforce_workgroup_configuration    = true
    publish_cloudwatch_metrics_enabled = true

    result_configuration {
      output_location = "s3://${aws_s3_bucket.athena_results.bucket}/results/"

      encryption_configuration {
        encryption_option = "SSE_S3"
      }
    }
  }

  force_destroy = true
}

resource "aws_athena_named_query" "dim_products_preview" {
  name        = "${var.project_prefix}-dim-products-preview"
  database    = aws_glue_catalog_database.classicmodels.name
  workgroup   = aws_athena_workgroup.task3.id
  description = "Subsecao 4.2 - exploracao em dim_products"

  query = <<-EOT
    SELECT
        product_id,
        product_name,
        product_line,
        product_vendor
    FROM dim_products
    LIMIT 20
  EOT
}

resource "aws_athena_named_query" "sales_by_country" {
  name        = "${var.project_prefix}-sales-by-country"
  database    = aws_glue_catalog_database.classicmodels.name
  workgroup   = aws_athena_workgroup.task3.id
  description = "Subsecao 4.3 - vendas totais por pais"

  query = <<-EOT
    SELECT
        dim_countries.country,
        SUM(fact_orders.sales_amount) AS total_sales
    FROM fact_orders
    JOIN dim_countries ON fact_orders.country_key = dim_countries.country_key
    GROUP BY dim_countries.country
    ORDER BY total_sales DESC
    LIMIT 10
  EOT
}

resource "aws_athena_named_query" "sales_detail" {
  name        = "${var.project_prefix}-sales-detail"
  database    = aws_glue_catalog_database.classicmodels.name
  workgroup   = aws_athena_workgroup.task3.id
  description = "Subsecao 4.4 - detalhe data x linha x produto x pais"

  query = <<-EOT
    SELECT
        dim_dates.full_date,
        dim_products.product_line,
        dim_products.product_name,
        dim_countries.country,
        SUM(fact_orders.sales_amount) AS total_sales
    FROM fact_orders
    JOIN dim_products  ON fact_orders.product_id    = dim_products.product_id
    JOIN dim_countries ON fact_orders.country_key   = dim_countries.country_key
    JOIN dim_dates     ON fact_orders.order_date_key = dim_dates.date_key
    GROUP BY
        dim_dates.full_date,
        dim_products.product_line,
        dim_products.product_name,
        dim_countries.country
  EOT
}
