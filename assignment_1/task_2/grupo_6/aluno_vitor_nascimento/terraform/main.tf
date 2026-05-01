provider "aws" {
  region = "us-east-1"
}

variable "db_password" {
  description = "Senha do banco de dados RDS"
  type        = string
  sensitive   = true
}

variable "db_username" {
  description = "Username do banco de dados RDS"
  type        = string
  sensitive   = true
}

data "http" "my_ip" {
  url = "https://checkip.amazonaws.com/"
}

data "aws_vpc" "default" {
  default = true
}

resource "aws_security_group" "rds_sg" {
  name_prefix = "rds-sg-task2-"
  description = "Permitir trafego MySQL apenas para IP atual"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    from_port   = 3306
    to_port     = 3306
    protocol    = "tcp"
    cidr_blocks = ["${chomp(data.http.my_ip.response_body)}/32"]
    description = "Acesso restrito ao IP do desenvolvedor"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_db_instance" "mysql_task" {
  allocated_storage      = 10
  engine                 = "mysql"
  engine_version         = "8.0"
  instance_class         = "db.t3.micro"
  username               = var.db_username
  password               = var.db_password
  parameter_group_name   = "default.mysql8.0"
  skip_final_snapshot    = true
  publicly_accessible    = true
  vpc_security_group_ids = [aws_security_group.rds_sg.id]
}

resource "aws_s3_bucket" "datalake" {
  bucket_prefix = "fgv-datalake-vitor-"
  force_destroy = true
}

data "aws_iam_role" "lab_role" {
  name = "LabRole"
}

output "rds_endpoint" {
  value = aws_db_instance.mysql_task.endpoint
}

output "s3_bucket" {
  value = aws_s3_bucket.datalake.id
}

output "glue_role_arn" {
  value = data.aws_iam_role.lab_role.arn
}