terraform {
    required_providers {
        aws = {
            source = "hashicorp/aws"
            version = "~> 5.0"
        }
    }
}

# Lendo as configurações
locals {
    credentials = jsondecode(file("${path.module}/config/db_credentials.json"))
    endpoint = jsondecode(file("${path.module}/config/db_endpoint.json"))
    etl_cfg = jsondecode(file("${path.module}/config/etl_configs.json"))

    # Extraindo a variável do bucket
    bucket_name = local.etl_cfg.bucket_name
}

provider "aws" {
    region = local.etl_cfg.region
}

# Capturando a rede padrão do Lab
data "aws_vpc" "default" {
    default = true
}

data "aws_subnets" "default" {
    filter {
        name = "vpc-id"
        values = [data.aws_vpc.default.id]
    }
}

data "aws_subnet" "selected" {
    id = data.aws_subnets.default.ids[0]
}

# Capturando as tabelas de roteamento da VPC
data "aws_route_tables" "default" {
    vpc_id = data.aws_vpc.default.id
}

# Criando o bucket S3 e fazendo o upload do script
resource "aws_s3_bucket" "datalake" {
    bucket = local.bucket_name
    force_destroy = true
}

# Fazendo o upload automático do script de ETL para o S3
resource "aws_s3_object" "etl_script" {
    bucket = aws_s3_bucket.datalake.id
    key = "scripts/etl_job.py"
    source = "${path.module}/etl_job.py"
    etag = filemd5("${path.module}/etl_job.py")
}

# VPC endpoint para o S3
resource "aws_vpc_endpoint" "s3" {
    vpc_id = data.aws_vpc.default.id
    service_name = "com.amazonaws.us-east-1.s3"
    route_table_ids = data.aws_route_tables.default.ids
}

# Security group do Glue
resource "aws_security_group" "glue_sg" {
    name = "glue_vpc_connection_sg"
    description = "Security Group para o AWS Glue"
    vpc_id = data.aws_vpc.default.id

    ingress {
        from_port = 0
        to_port = 65535
        protocol = "tcp"
        self = true
    }

    # Regra exigida pelos nós do Glue para se comunicarem
    egress {
        from_port = 0
        to_port = 0
        protocol = "-1"
        self = true
    }

    # Saída para acessar o S3 e o RDS
    egress {
        from_port = 0
        to_port = 0
        protocol = "-1"
        cidr_blocks = ["0.0.0.0/0"]
    }
}

# Capturando a Role padrão do AWS Academy
data "aws_iam_role" "lab_role" {
    name = "LabRole"
}

# Conexão do Glue com o RDS
resource "aws_glue_connection" "rds_conn" {
    name = "rds_mysql_connection"

    connection_properties = {
        JDBC_CONNECTION_URL = "jdbc:mysql://${local.endpoint.host}:${local.endpoint.port}/classicmodels"
        USERNAME = local.credentials.db_user
        PASSWORD = local.credentials.db_password
    }

    physical_connection_requirements {
        security_group_id_list = [aws_security_group.glue_sg.id]
        subnet_id = data.aws_subnets.default.ids[0]
        availability_zone = data.aws_subnet.selected.availability_zone
    }
}

# Job do Glue
resource "aws_glue_job" "etl_job" {
    name = "classicmodels_star_schema_etl"
    role_arn = data.aws_iam_role.lab_role.arn

    command {
        script_location = "s3://${aws_s3_bucket.datalake.bucket}/${aws_s3_object.etl_script.key}"
        python_version = "3"
    }

    default_arguments = {
        "--JOB_NAME" = "classicmodels_star_schema_etl"
        "--S3_TARGET_PATH" = "s3://${aws_s3_bucket.datalake.bucket}/output"
        "--TempDir" = "s3://${aws_s3_bucket.datalake.bucket}/temp"
        "--job-language" = "python"
    }

    connections = [aws_glue_connection.rds_conn.name]

    # Configurações de performance/custo
    glue_version = "4.0"
    worker_type = "G.1X"
    number_of_workers = 2
    max_retries = 0
}