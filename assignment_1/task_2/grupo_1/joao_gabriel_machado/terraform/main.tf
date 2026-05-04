terraform {
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

# Busca a VPC Padrão existente na sua conta da AWS
data "aws_vpc" "default" {
  default = true
}

# Cria o Security Group
resource "aws_security_group" "rds_sg" {
  name        = "sales-analytics-sg"
  description = "Security group para o RDS Sales Analytics"
  vpc_id      = data.aws_vpc.default.id

  # Regra Inbound 1: Seu IP Local
  ingress {
    from_port   = 3306
    to_port     = 3306
    protocol    = "tcp"
    cidr_blocks = [var.my_ip]
    description = "Acesso local do Engenheiro de Dados"
  }

  # Regra Inbound 2: Tráfego Interno da VPC (para o AWS Glue futuramente)
  ingress {
    from_port   = 3306
    to_port     = 3306
    protocol    = "tcp"
    cidr_blocks = [data.aws_vpc.default.cidr_block]
    description = "Acesso interno para servicos AWS na mesma VPC"
  }

  # Regra Outbound: Permite que o RDS responda para a internet
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# Cria a Instância RDS
resource "aws_db_instance" "sales_analytics" {
  identifier           = var.db_identifier
  allocated_storage    = 20
  engine               = "mysql"
  engine_version       = "8.0"
  instance_class       = "db.t3.micro"
  username             = var.db_user
  password             = var.db_password
  parameter_group_name = "default.mysql8.0"
  skip_final_snapshot  = true
  publicly_accessible  = true

  vpc_security_group_ids = [aws_security_group.rds_sg.id]
}