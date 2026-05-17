provider "aws" {
  region = var.region
}

# S3
resource "aws_s3_bucket" "data_lake" {
  bucket = var.bucket_name
}

# IAM Role
resource "aws_iam_role" "glue_role" {
  name = "glue-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "glue.amazonaws.com"
      }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "glue_policy" {
  role       = aws_iam_role.glue_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole"
}

# Glue Connection
resource "aws_glue_connection" "mysql_conn" {
  name = "mysql-connection"

  connection_properties = {
    JDBC_CONNECTION_URL = "jdbc:mysql://<RDS-ENDPOINT>:3306/classicmodels"
    USERNAME            = "admin"
    PASSWORD            = "Admin1234!"
  }

  physical_connection_requirements {
    availability_zone      = "us-east-1a"
    security_group_id_list = []
    subnet_id              = ""
  }
}

# Glue Job
resource "aws_glue_job" "etl_job" {
  name     = "classicmodels-etl"
  role_arn = aws_iam_role.glue_role.arn

  command {
    script_location = "s3://${var.bucket_name}/scripts/etl_job.py"
    python_version  = "3"
  }

  glue_version = "3.0"
}