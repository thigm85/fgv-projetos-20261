provider "aws" {
  region = var.aws_region
}

# Data Sources

# busca o Security Group pelo nome
data "aws_security_group" "rds_sg" {
  name = var.sg_name
}

# busca a VPC Padrão da conta
data "aws_vpc" "default" {
  default = true
}

# busca as Subnets dentro dessa VPC Padrão
data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

# Pega informações da primeira Subnet encontrada (necessário para a AZ)
data "aws_subnet" "first" {
  id = data.aws_subnets.default.ids[0]
}

# Resources ETL

resource "aws_s3_bucket" "datalake" {
  bucket = var.bucket_name
  force_destroy = true 
}

resource "aws_iam_role" "glue_role" {
  name = "glue-etl-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = { Service = "glue.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "glue_service" {
  role = aws_iam_role.glue_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole"
}

resource "aws_iam_role_policy_attachment" "glue_s3" {
  role = aws_iam_role.glue_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonS3FullAccess" 
}

# Conexão do Glue usando os Data Sources para preencher a rede
resource "aws_glue_connection" "rds_conn" {
  name = "classicmodels-rds-conn"
  connection_properties = {
    JDBC_CONNECTION_URL = "jdbc:mysql://${var.db_endpoint}:3306/${var.db_name}"
    USERNAME = var.db_username
    PASSWORD = var.db_password
  }

  physical_connection_requirements {
    availability_zone      = data.aws_subnet.first.availability_zone
    security_group_id_list = [data.aws_security_group.rds_sg.id]
    subnet_id              = data.aws_subnet.first.id
  }
}

resource "aws_glue_job" "etl_job" {
  name = "classicmodels-star-schema-job"
  role_arn = aws_iam_role.glue_role.arn
  connections = [aws_glue_connection.rds_conn.name]

  command {
    name = "glueetl"
    script_location = "s3://${aws_s3_bucket.datalake.bucket}/scripts/etl_script.py"
    python_version = "3"
  }

  default_arguments = {
    "--job-language" = "python"
    "--TempDir" = "s3://${aws_s3_bucket.datalake.bucket}/temp/"
  }

  glue_version = "4.0"
  worker_type = "G.1X"
  number_of_workers = 2
}