data "aws_caller_identity" "current" {}

locals {
  name_prefix = var.project_name

  tags = {
    Project = var.project_name
    Owner   = "grupo_4"
    Task    = "assignment_2_task_2"
  }

  # Keep within 63 chars, lowercase; unique per account.
  bucket_name = lower(replace("${var.project_name}-${data.aws_caller_identity.current.account_id}", "_", "-"))

  scripts_prefix   = "glue/scripts"
  analytics_prefix = "analytics"

  pipeline_name   = "classicmodels_sales"
  watermark_table = "etl_watermark"
}

