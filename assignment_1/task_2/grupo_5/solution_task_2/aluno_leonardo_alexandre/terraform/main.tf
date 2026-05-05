resource "random_id" "suffix" {
  byte_length = 4
}

data "aws_subnet" "selected" {
  id = var.subnet_id
}

data "aws_route_tables" "selected_vpc" {
  vpc_id = var.vpc_id
}

resource "aws_s3_bucket" "etl_bucket" {
  bucket = "${var.project_name}-${random_id.suffix.hex}"
}

resource "aws_vpc_endpoint" "s3_gateway" {
  vpc_id            = var.vpc_id
  service_name      = "com.amazonaws.${var.aws_region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = data.aws_route_tables.selected_vpc.ids
}

resource "aws_s3_bucket_versioning" "etl_bucket_versioning" {
  bucket = aws_s3_bucket.etl_bucket.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "etl_bucket_sse" {
  bucket = aws_s3_bucket.etl_bucket.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_security_group" "glue_job_sg" {
  name        = "${var.project_name}-glue-sg"
  description = "Security group for Glue JDBC connection"
  vpc_id      = var.vpc_id
}

resource "aws_security_group_rule" "glue_egress_all" {
  type              = "egress"
  from_port         = 0
  to_port           = 0
  protocol          = "-1"
  cidr_blocks       = ["0.0.0.0/0"]
  security_group_id = aws_security_group.glue_job_sg.id
}

resource "aws_security_group_rule" "glue_egress_self" {
  type                     = "egress"
  from_port                = 0
  to_port                  = 65535
  protocol                 = "tcp"
  security_group_id        = aws_security_group.glue_job_sg.id
  source_security_group_id = aws_security_group.glue_job_sg.id
}

resource "aws_security_group_rule" "glue_ingress_self" {
  type                     = "ingress"
  from_port                = 0
  to_port                  = 65535
  protocol                 = "tcp"
  security_group_id        = aws_security_group.glue_job_sg.id
  source_security_group_id = aws_security_group.glue_job_sg.id
}

resource "aws_security_group_rule" "allow_glue_to_rds" {
  type                     = "ingress"
  from_port                = var.db_port
  to_port                  = var.db_port
  protocol                 = "tcp"
  security_group_id        = var.db_security_group_id
  source_security_group_id = aws_security_group.glue_job_sg.id
}

resource "aws_s3_object" "glue_script" {
  bucket       = aws_s3_bucket.etl_bucket.id
  key          = "scripts/etl_job.py"
  source       = "${path.module}/../glue/etl_job.py"
  etag         = filemd5("${path.module}/../glue/etl_job.py")
  content_type = "text/x-python"
}

resource "aws_glue_connection" "mysql_connection" {
  name = "${var.project_name}-mysql-connection"

  connection_properties = {
    JDBC_CONNECTION_URL = "jdbc:mysql://${var.db_host}:${var.db_port}/${var.db_name}"
    USERNAME            = var.db_user
    PASSWORD            = var.db_password
  }

  physical_connection_requirements {
    availability_zone      = data.aws_subnet.selected.availability_zone
    security_group_id_list = [aws_security_group.glue_job_sg.id]
    subnet_id              = var.subnet_id
  }
}

resource "aws_glue_job" "etl_job" {
  name     = "${var.project_name}-etl-job"
  role_arn = var.glue_role_arn

  command {
    script_location = "s3://${aws_s3_bucket.etl_bucket.id}/${aws_s3_object.glue_script.key}"
    python_version  = "3"
  }

  glue_version      = "4.0"
  worker_type       = "G.1X"
  number_of_workers = 2
  timeout           = 30
  max_retries       = 0
  connections       = [aws_glue_connection.mysql_connection.name]

  default_arguments = {
    "--job-language"             = "python"
    "--TempDir"                  = "s3://${aws_s3_bucket.etl_bucket.id}/temp/"
    "--enable-glue-datacatalog"  = "true"
    "--db_host"                  = var.db_host
    "--db_port"                  = tostring(var.db_port)
    "--db_name"                  = var.db_name
    "--db_user"                  = var.db_user
    "--db_password"              = var.db_password
    "--output_s3_path"           = "s3://${aws_s3_bucket.etl_bucket.id}/curated/"
  }
}
