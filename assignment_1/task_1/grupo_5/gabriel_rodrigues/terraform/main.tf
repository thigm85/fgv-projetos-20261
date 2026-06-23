terraform {
  required_version = ">= 1.0"

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

data "aws_db_subnet_group" "this" {
  name = var.db_subnet_group_name
}

resource "aws_security_group" "rds_mysql" {
  name        = "${var.db_identifier}-mysql"
  description = "MySQL: liberado para CIDRs em allowed_cidr_blocks e SGs em allowed_security_group_ids"

  vpc_id = data.aws_db_subnet_group.this.vpc_id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_vpc_security_group_ingress_rule" "mysql_from_cidr" {
  for_each = toset(var.allowed_cidr_blocks)

  security_group_id = aws_security_group.rds_mysql.id
  description         = "MySQL a partir do CIDR ${each.value}"
  ip_protocol         = "tcp"
  from_port           = 3306
  to_port             = 3306
  cidr_ipv4           = each.value
}

resource "aws_vpc_security_group_ingress_rule" "mysql_from_sg" {
  for_each = toset(var.allowed_security_group_ids)

  security_group_id            = aws_security_group.rds_mysql.id
  description                  = "MySQL a partir do SG ${each.value}"
  ip_protocol                  = "tcp"
  from_port                    = 3306
  to_port                      = 3306
  referenced_security_group_id = each.value
}

resource "aws_db_instance" "this" {
  identifier     = var.db_identifier
  engine         = "mysql"
  engine_version = "8.0"
  instance_class = "db.t3.micro"

  allocated_storage = 20
  storage_type      = "gp2"

  username = var.db_username
  password = var.db_password

  db_subnet_group_name   = data.aws_db_subnet_group.this.name
  vpc_security_group_ids = [aws_security_group.rds_mysql.id]
  publicly_accessible    = true

  skip_final_snapshot = true
}
