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
  vpc_security_group_ids = []    # Assume default VPC; ajuste se necessário

  tags = {
    Name = "ClassicModels RDS"
  }
}