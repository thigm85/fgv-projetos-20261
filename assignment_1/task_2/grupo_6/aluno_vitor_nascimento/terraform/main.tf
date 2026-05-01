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

data "aws_vpc" "default" {
  default = true
}

resource "aws_security_group" "rds_sg" {
  name        = "rds_mysql_sg"
  description = "Permitir trafego MySQL local"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    from_port   = 3306
    to_port     = 3306
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_db_instance" "mysql_task" {
  allocated_storage      = 10
  engine                 = "mysql"
  engine_version         = "8.0"
  instance_class         = "db.t3.micro"
  identifier             = "projetos-db"
  username               = var.db_username
  password               = var.db_password
  parameter_group_name   = "default.mysql8.0"
  skip_final_snapshot    = true
  publicly_accessible    = true
  vpc_security_group_ids = [aws_security_group.rds_sg.id]
}

output "rds_endpoint" {
  value = aws_db_instance.mysql_task.endpoint
}