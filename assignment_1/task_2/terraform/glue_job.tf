##############################################################################
# AWS Glue Job — ETL classicmodels (MySQL → Star Schema → Parquet no S3)
#
# - Glue 4.0 (PySpark 3, Python 3)
# - 2 workers G.1X (mínimo para lab)
# - Timeout de 30 minutos
# - Passa bucket de saída e nome da conexão como argumentos do job
##############################################################################

resource "aws_glue_job" "etl_classicmodels" {
  name     = "${var.project_name}-job"
  role_arn = data.aws_iam_role.lab_role.arn

  glue_version      = "4.0"
  worker_type       = "G.1X"
  number_of_workers = 2
  timeout           = 30 # minutos

  command {
    name            = "glueetl"
    script_location = "s3://${aws_s3_bucket.glue_assets.id}/scripts/etl_classicmodels.py"
    python_version  = "3"
  }

  connections = [aws_glue_connection.mysql_rds.name]

  default_arguments = {
    "--job-language"                     = "python"
    "--TempDir"                          = "s3://${aws_s3_bucket.glue_assets.id}/temp/"
    "--OUTPUT_BUCKET"                    = aws_s3_bucket.etl_output.id
    "--CONNECTION_NAME"                  = aws_glue_connection.mysql_rds.name
    "--enable-metrics"                   = "true"
    "--enable-continuous-cloudwatch-log" = "true"
  }

  tags = {
    Project = var.project_name
  }
}
