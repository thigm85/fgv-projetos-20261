data "aws_subnet" "glue" {
  id = var.subnet_id
}

resource "aws_glue_connection" "mysql" {
  name            = "${local.name_prefix}-mysql-conn"
  connection_type = "JDBC"

  connection_properties = {
    JDBC_CONNECTION_URL = "jdbc:mysql://${var.rds_endpoint}:${var.rds_port}/${var.db_name}"
    USERNAME            = var.db_user
    PASSWORD            = var.db_password
  }

  physical_connection_requirements {
    availability_zone      = data.aws_subnet.glue.availability_zone
    security_group_id_list = local.glue_connection_sg_ids
    subnet_id              = var.subnet_id
  }

  tags = local.tags
}

resource "aws_s3_object" "glue_script" {
  bucket       = aws_s3_bucket.etl.id
  key          = "${local.scripts_prefix}/classicmodels_star_etl.py"
  source       = "${path.module}/glue_job_script.py"
  source_hash  = filemd5("${path.module}/glue_job_script.py")
  content_type = "text/x-python"

  depends_on = [
    aws_s3_bucket_ownership_controls.etl,
    aws_s3_bucket_public_access_block.etl,
  ]
}

resource "aws_glue_job" "etl" {
  name     = "${local.name_prefix}-job"
  role_arn = data.aws_iam_role.glue.arn

  glue_version      = "4.0"
  worker_type       = "G.1X"
  number_of_workers = 2

  command {
    name            = "glueetl"
    python_version  = "3"
    script_location = "s3://${aws_s3_bucket.etl.bucket}/${aws_s3_object.glue_script.key}"
  }

  default_arguments = {
    "--job-language"                     = "python"
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-glue-datacatalog"          = "false"
    "--enable-metrics"                   = "true"

    "--rds_endpoint" = var.rds_endpoint
    "--rds_port"     = tostring(var.rds_port)
    "--db_name"      = var.db_name
    "--db_user"      = var.db_user
    "--db_password"  = var.db_password
    "--s3_bucket"    = aws_s3_bucket.etl.bucket
    "--out_prefix"   = local.out_prefix
  }

  connections = [aws_glue_connection.mysql.name]
  tags        = local.tags
}

