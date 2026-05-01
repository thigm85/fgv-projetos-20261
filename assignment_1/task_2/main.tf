terraform {
    required_providers {
        aws = {
            source = "hashicorp/aws"
            version = "~> 5.0"
        }
    }
}

provider "aws" {
    region = "us-east-1"
}

# Lendo as configurações
locals {
    credentials = jsondecode(file("${path.module}/config/db_credentials.json"))
    endpoint = jsondecode(file("${path.module}/config/db_endpoint.json"))
    bucket_name = "classicmodels-datalake-pedro-coterli"
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

    egress {
        from_port = 0
        to_port = 0
        protocol = "-1"
        cidr_blocks = ["0.0.0.0/0"]
    }
}