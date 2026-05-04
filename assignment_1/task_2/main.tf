terraform {
  required_version = ">= 1.3.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

data "aws_caller_identity" "current" {}

resource "aws_s3_bucket" "datalake" {
  bucket        = var.s3_bucket_name
  force_destroy = true

  tags = {
    Name    = var.s3_bucket_name
    Project = "classicmodels-pipeline"
  }
}

resource "aws_s3_bucket_versioning" "datalake" {
  bucket = aws_s3_bucket.datalake.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "datalake" {
  bucket = aws_s3_bucket.datalake.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_object" "glue_script" {
  bucket = aws_s3_bucket.datalake.id
  key    = "scripts/etl_job.py"
  source = "${path.module}/glue/etl_job.py"
  etag   = filemd5("${path.module}/glue/etl_job.py")
}

data "aws_vpc" "rds_vpc" {
  id = "vpc-0095827a32a6faa09"
}

resource "aws_security_group" "glue_sg" {
  name        = "glue-classicmodels-sg"
  description = "Security group for Glue workers"
  vpc_id      = data.aws_vpc.rds_vpc.id

  ingress {
    from_port = 0
    to_port   = 65535
    protocol  = "tcp"
    self      = true
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name    = "glue-classicmodels-sg"
    Project = "classicmodels-pipeline"
  }
}

resource "aws_security_group_rule" "glue_to_rds" {
  type                     = "ingress"
  from_port                = var.rds_port
  to_port                  = var.rds_port
  protocol                 = "tcp"
  security_group_id        = var.rds_security_group_id
  source_security_group_id = aws_security_group.glue_sg.id
  description              = "Allow Glue workers to access RDS MySQL"
}

resource "aws_glue_connection" "rds_connection" {
  name = var.glue_connection_name

  connection_type = "JDBC"

  connection_properties = {
    JDBC_CONNECTION_URL = "jdbc:mysql://${var.rds_endpoint}:${var.rds_port}/${var.rds_db_name}"
    USERNAME            = var.rds_username
    PASSWORD            = var.rds_password
  }

  physical_connection_requirements {
    subnet_id              = "subnet-0f8cd4c4e1601c933"
    security_group_id_list = [aws_security_group.glue_sg.id]
  }

  tags = {
    Project = "classicmodels-pipeline"
  }
}

resource "aws_glue_job" "etl_job" {
  name         = var.glue_job_name
  role_arn = "arn:aws:iam::975049962812:role/LabRole"
  glue_version = "4.0"

  command {
    name            = "glueetl"
    script_location = "s3://${aws_s3_bucket.datalake.bucket}/scripts/etl_job.py"
    python_version  = "3"
  }

  connections = [aws_glue_connection.rds_connection.name]

  default_arguments = {
    "--job-language"                     = "python"
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-spark-ui"                  = "true"
    "--spark-event-logs-path"            = "s3://${aws_s3_bucket.datalake.bucket}/spark-logs/"
    "--enable-job-insights"              = "true"
    "--job-bookmark-option"              = "job-bookmark-disable"
    "--TempDir"                          = "s3://${aws_s3_bucket.datalake.bucket}/tmp/"
    "--S3_OUTPUT_PATH"      = "s3://${aws_s3_bucket.datalake.bucket}/data/"
    "--DB_NAME"             = var.rds_db_name
    "--CONNECTION_NAME"     = var.glue_connection_name
    "--JDBC_URL"            = "jdbc:mysql://${var.rds_endpoint}:${var.rds_port}/${var.rds_db_name}"
    "--DB_USER"             = var.rds_username
    "--DB_PASSWORD"         = var.rds_password
  }

  number_of_workers = 2
  worker_type       = "G.1X"
  timeout           = 60

  tags = {
    Project = "classicmodels-pipeline"
  }

  depends_on = [
    aws_s3_object.glue_script,
    aws_glue_connection.rds_connection
  ]
}
