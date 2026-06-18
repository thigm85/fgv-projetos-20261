resource "aws_glue_connection" "mysql" {
  name = "${var.project_name}-mysql-connection"
  connection_type = "JDBC"

  connection_properties = {
    JDBC_CONNECTION_URL = "jdbc:mysql://${local.rds_endpoint}/${var.rds_database}"
    USERNAME = var.rds_username
    PASSWORD = var.rds_password
  }

  physical_connection_requirements {
    availability_zone = local.rds_availability_zone
    security_group_id_list = [local.rds_security_group_id]
    subnet_id = local.rds_subnet_id
  }
}

resource "aws_s3_object" "etl_script" {
  bucket = aws_s3_bucket.data_lake.id
  key = "scripts/etl_job.py"
  source = "${path.module}/etl_job.py"
  etag = filemd5("${path.module}/etl_job.py")
}

resource "aws_glue_job" "etl" {
  name = "${var.project_name}-etl-job"
  role_arn = data.aws_iam_role.lab_role.arn

  command {
    script_location = "s3://${aws_s3_bucket.data_lake.id}/scripts/etl_job.py"
    python_version  = "3"
  }

  default_arguments = {
    "--job-language" = "python"
    "--S3_OUTPUT_PATH" = "s3://${aws_s3_bucket.data_lake.id}/output"
    "--JDBC_CONNECTION_URL" = "jdbc:mysql://${local.rds_endpoint}/${var.rds_database}"
    "--DB_USER" = var.rds_username
    "--DB_PASSWORD" = var.rds_password
    "--DB_NAME" = var.rds_database
    "--CONNECTION_NAME" = aws_glue_connection.mysql.name
    "--enable-metrics" = "true"
    "--enable-spark-ui" = "true"
    "--spark-event-logs-path" = "s3://${aws_s3_bucket.data_lake.id}/spark-logs"
  }

  connections = [aws_glue_connection.mysql.name]

  glue_version = "4.0"
  number_of_workers = 2
  worker_type = "G.1X"

  timeout = 10
}
