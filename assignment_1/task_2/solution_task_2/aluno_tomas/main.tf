terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

locals {
  output_path = "s3://${var.bucket_name}/${var.output_prefix}"
}

variable "region" {
  type    = string
  default = "us-east-1"
}

variable "bucket_name" {
  type = string
}

variable "job_name" {
  type = string
}

variable "output_prefix" {
  type    = string
  default = "output"
}

variable "db_host" {
  type = string
}

variable "db_port" {
  type    = number
  default = 3306
}

variable "db_name" {
  type = string
}

variable "db_user" {
  type = string
}

variable "db_password" {
  type      = string
  sensitive = true
}

variable "db_security_group_id" {
  type = string
}

provider "aws" {
  region = var.region
}

data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

data "aws_subnet" "selected" {
  id = data.aws_subnets.default.ids[0]
}

data "aws_route_tables" "default" {
  vpc_id = data.aws_vpc.default.id
}

data "aws_iam_role" "lab_role" {
  name = "LabRole"
}

resource "aws_s3_bucket" "datalake" {
  bucket        = var.bucket_name
  force_destroy = true

  tags = {
    Project = "assignment-1-task-2"
    Group   = "grupo-5"
  }
}

resource "aws_s3_object" "etl_script" {
  bucket       = aws_s3_bucket.datalake.id
  key          = "scripts/etl_job.py"
  source       = "${path.module}/etl_job.py"
  etag         = filemd5("${path.module}/etl_job.py")
  content_type = "text/x-python"
}

resource "aws_vpc_endpoint" "s3" {
  vpc_id            = data.aws_vpc.default.id
  service_name      = "com.amazonaws.${var.region}.s3"
  route_table_ids   = data.aws_route_tables.default.ids
  vpc_endpoint_type = "Gateway"
}

resource "aws_security_group" "glue_sg" {
  name        = "grupo-5-glue-vpc-connection-sg"
  description = "Security group for Grupo 5 Glue ETL"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description = "Glue worker self communication"
    from_port   = 0
    to_port     = 65535
    protocol    = "tcp"
    self        = true
  }

  egress {
    description = "Outbound access to RDS and S3 endpoint"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group_rule" "rds_from_glue" {
  type                     = "ingress"
  from_port                = var.db_port
  to_port                  = var.db_port
  protocol                 = "tcp"
  security_group_id        = var.db_security_group_id
  source_security_group_id = aws_security_group.glue_sg.id
  description              = "Allow Glue to read Grupo 5 classicmodels source"
}

resource "aws_glue_connection" "rds_conn" {
  name            = "grupo-5-rds-mysql-connection"
  connection_type = "JDBC"

  connection_properties = {
    JDBC_CONNECTION_URL = "jdbc:mysql://${var.db_host}:${var.db_port}/${var.db_name}"
    USERNAME            = var.db_user
    PASSWORD            = var.db_password
  }

  physical_connection_requirements {
    security_group_id_list = [aws_security_group.glue_sg.id]
    subnet_id              = data.aws_subnets.default.ids[0]
    availability_zone      = data.aws_subnet.selected.availability_zone
  }
}

resource "aws_glue_job" "etl_job" {
  name              = var.job_name
  role_arn          = data.aws_iam_role.lab_role.arn
  glue_version      = "4.0"
  worker_type       = "G.1X"
  number_of_workers = 2
  max_retries       = 0
  connections       = [aws_glue_connection.rds_conn.name]

  command {
    name            = "glueetl"
    script_location = "s3://${aws_s3_bucket.datalake.bucket}/${aws_s3_object.etl_script.key}"
    python_version  = "3"
  }

  default_arguments = {
    "--JOB_NAME"        = var.job_name
    "--S3_TARGET_PATH"  = local.output_path
    "--CONNECTION_NAME" = aws_glue_connection.rds_conn.name
    "--TempDir"         = "s3://${aws_s3_bucket.datalake.bucket}/temp"
    "--job-language"    = "python"
  }
}

output "bucket_name" {
  value = aws_s3_bucket.datalake.bucket
}

output "output_path" {
  value = local.output_path
}

output "glue_job_name" {
  value = aws_glue_job.etl_job.name
}
