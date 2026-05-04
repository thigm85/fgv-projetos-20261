##############################################################################
# Data Sources — Detecta automaticamente a infraestrutura da Task 1
#
# Lê a instância RDS, VPC, subnets e security groups já existentes
# para que o Terraform da Task 2 não precise de valores manuais.
##############################################################################

data "aws_caller_identity" "current" {}

# ─── RDS Instance (criada na Task 1 via provision_rds.py) ───────────────────
data "aws_db_instance" "classicmodels" {
  db_instance_identifier = var.rds_instance_id
}

# ─── VPC padrão (usada pela Task 1) ────────────────────────────────────────
data "aws_vpc" "default" {
  default = true
}

# ─── Subnets da VPC padrão ─────────────────────────────────────────────────
data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

# Pega detalhes da primeira subnet (para AZ)
data "aws_subnet" "first" {
  id = data.aws_subnets.default.ids[0]
}

# ─── Security Group do RDS (criado pela Task 1) ────────────────────────────
data "aws_security_group" "rds_sg" {
  filter {
    name   = "group-name"
    values = ["rds-classicmodels-sg"]
  }
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

# ─── Locals com valores extraídos ──────────────────────────────────────────
locals {
  rds_endpoint      = data.aws_db_instance.classicmodels.address
  rds_port          = data.aws_db_instance.classicmodels.port
  rds_username      = data.aws_db_instance.classicmodels.master_username
  vpc_id            = data.aws_vpc.default.id
  subnet_id         = data.aws_subnet.first.id
  availability_zone = data.aws_subnet.first.availability_zone
  security_group_id = data.aws_security_group.rds_sg.id
}
