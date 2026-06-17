locals {
  sagemaker_on_start = var.enable_sagemaker_notebook ? base64encode(
    replace(
      replace(
        replace(
          replace(
            replace(
              replace(
                replace(
                  file("${path.module}/../sagemaker/on_start.sh"),
                  "__ETL_BUCKET__", aws_s3_bucket.etl_bucket.bucket,
                ),
                "__NOTEBOOK_KEY__", local.notebook_bucket_key,
              ),
              "__GLUE_DATABASE__", aws_glue_catalog_database.classicmodels.name,
            ),
            "__ATHENA_WORKGROUP__", aws_athena_workgroup.task3.name,
          ),
          "__ATHENA_OUTPUT_S3__", "s3://${aws_s3_bucket.athena_results.bucket}/results/",
        ),
        "__DB_SECRET_ID__", aws_secretsmanager_secret.db_credentials.name,
      ),
      "__AWS_REGION__", var.aws_region,
    )
  ) : ""
}

resource "aws_sagemaker_notebook_instance_lifecycle_configuration" "task3" {
  count = var.enable_sagemaker_notebook ? 1 : 0

  name      = "${var.project_prefix}-lifecycle"
  on_start  = local.sagemaker_on_start
  on_create = local.sagemaker_on_start
}

resource "aws_sagemaker_notebook_instance" "task3" {
  count = var.enable_sagemaker_notebook ? 1 : 0

  name                  = "${var.project_prefix}-notebook"
  role_arn              = local.lab_role_arn
  instance_type         = var.sagemaker_instance_type
  volume_size           = var.sagemaker_volume_size_gb
  lifecycle_config_name = aws_sagemaker_notebook_instance_lifecycle_configuration.task3[0].name
  platform_identifier   = "notebook-al2-v2"

  root_access            = "Enabled"
  direct_internet_access = "Enabled"

  tags = {
    Purpose = "task3-dashboard"
  }

  depends_on = [
    aws_s3_object.notebook,
    aws_glue_catalog_table.tables,
    aws_athena_workgroup.task3,
    aws_secretsmanager_secret_version.db_credentials,
  ]
}
