terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.region
}

# Reference existing RDS instance
data "aws_db_instance" "classicmodels_rds" {
  db_instance_identifier = var.db_identifier
}

# Reference existing security group
data "aws_security_group" "rds_sg" {
  filter {
    name   = "group-name"
    values = ["rds-mysql-sg-*"]
  }
}

# S3 Bucket for Data Lake
resource "aws_s3_bucket" "data_lake" {
  bucket = var.s3_bucket_name

  tags = {
    Name = "ClassicModels Data Lake"
  }
}

# Glue Catalog Database
resource "aws_glue_catalog_database" "classicmodels" {
  name = var.glue_database_name
}

# Glue Job - Using existing lab role
resource "aws_glue_job" "etl_job" {
  name     = var.glue_job_name
  role_arn = "arn:aws:iam::353410101323:role/LabRole"  # Using existing lab role

  command {
    script_location = "s3://${aws_s3_bucket.data_lake.bucket}/scripts/etl_transform.py"
    python_version  = "3"
  }

  default_arguments = {
    "--job-bookmark-option"     = "job-bookmark-enable"
    "--enable-metrics"          = ""
    "--rds_endpoint"            = data.aws_db_instance.classicmodels_rds.endpoint
    "--db_name"                 = var.db_name
    "--db_user"                 = var.username
    "--db_password"             = var.password
    "--s3_output_path"          = "s3://${aws_s3_bucket.data_lake.bucket}/data/"
    "--enable-glue-datacatalog" = ""
  }

  max_retries = 0
  timeout     = 30
}