resource "aws_glue_catalog_database" "star" {
  name        = var.glue_database_name
  description = "Star schema for classicmodels ETL (Task 2/3)"
}
