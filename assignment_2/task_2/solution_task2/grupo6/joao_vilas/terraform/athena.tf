resource "aws_athena_workgroup" "a2t2" {
  name        = "${var.project_prefix}-wg"
  description = "Workgroup do Athena para validar fact_orders particionado"
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

# Consulta de exemplo com filtro de partição (pruning visível no Athena).
resource "aws_athena_named_query" "sales_by_partition" {
  name        = "${var.project_prefix}-sales-by-partition"
  database    = aws_glue_catalog_database.classicmodels.name
  workgroup   = aws_athena_workgroup.a2t2.id
  description = "Vendas por ano/mes usando as partition keys order_year/order_month"

  query = <<-EOT
    SELECT
        order_year,
        order_month,
        COUNT(*)            AS line_items,
        SUM(sales_amount)   AS total_sales
    FROM fact_orders
    WHERE order_year >= 2003
    GROUP BY order_year, order_month
    ORDER BY order_year, order_month
  EOT
}
