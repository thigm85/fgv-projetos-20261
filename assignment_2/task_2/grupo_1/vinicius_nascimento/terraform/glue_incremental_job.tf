# Upload do script para S3 e definição do Glue Job incremental.
# Se você já tem aws_glue_job no A1, pode substituir o script_location e default_arguments nele.

resource "aws_s3_object" "classicmodels_incremental_glue_script" {
  bucket = var.scripts_bucket
  key    = "glue/incremental_sales_job.py"
  source = "${path.module}/../glue/incremental_sales_job.py"
  etag   = filemd5("${path.module}/../glue/incremental_sales_job.py")
}

resource "aws_glue_job" "classicmodels_sales_incremental" {
  name     = var.glue_job_name
  role_arn = var.glue_role_arn

  glue_version      = "4.0"
  worker_type       = "G.1X"
  number_of_workers = 2
  timeout           = 30

  command {
    name            = "glueetl"
    script_location = "s3://${var.scripts_bucket}/${aws_s3_object.classicmodels_incremental_glue_script.key}"
    python_version  = "3"
  }

  default_arguments = {
    "--job-language"                     = "python"
    "--enable-glue-datacatalog"          = "true"
    "--enable-metrics"                   = "true"
    "--enable-continuous-cloudwatch-log" = "true"
    "--jdbc_url"                         = var.jdbc_url
    "--jdbc_user"                        = var.jdbc_user
    "--jdbc_password"                    = var.jdbc_password
    "--s3_analytics_path"                = "s3://${var.analytics_bucket}/analytics"
    "--glue_database"                    = var.glue_database_name
    "--pipeline_name"                    = "classicmodels_sales"
  }
}
