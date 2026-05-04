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

resource "aws_security_group" "rds_sg" {
  name_prefix = "rds-mysql-sg-"
  description = "Security group for RDS MySQL instance"

  ingress {
    from_port   = 3306
    to_port     = 3306
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]  # Permite acesso de qualquer lugar; em produção, restrinja
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "RDS MySQL Security Group"
  }
}

resource "aws_db_instance" "classicmodels_rds" {
  identifier             = var.db_identifier
  allocated_storage      = var.allocated_storage
  db_name                = var.db_name
  engine                 = "mysql"
  engine_version         = var.engine_version
  instance_class         = var.instance_class
  username               = var.username
  password               = var.password
  publicly_accessible    = true  # Para acesso local; em produção, false
  skip_final_snapshot    = true  # Para facilitar destruição; em produção, false
  vpc_security_group_ids = [aws_security_group.rds_sg.id]  # Security group para permitir acesso na porta 3306

  tags = {
    Name = "ClassicModels RDS"
  }
}