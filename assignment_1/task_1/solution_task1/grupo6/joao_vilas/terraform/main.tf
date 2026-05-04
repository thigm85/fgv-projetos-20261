provider "aws" {
  region = var.aws_region
}

resource "aws_security_group" "rds_sg" {
  name        = "${var.db_identifier}-sg"
  description = "Permitir acesso restrito ao RDS MySQL no laboratorio"

  ingress {
    description = "MySQL somente a partir do IP publico autorizado"
    from_port   = 3306
    to_port     = 3306
    protocol    = "tcp"
    cidr_blocks = [var.allowed_mysql_cidr]
  }

  egress {
    description = "Saida liberada"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Project = "classicmodels-task1"
    Owner   = "grupo6-joao-vilas"
  }
}

resource "aws_db_instance" "classicmodels_db" {
  identifier             = var.db_identifier
  allocated_storage      = 20
  engine                 = "mysql"
  engine_version         = "8.0"
  instance_class         = "db.t3.micro"
  username               = var.db_username
  password               = var.db_password
  parameter_group_name   = "default.mysql8.0"
  skip_final_snapshot    = true
  publicly_accessible    = true
  vpc_security_group_ids = [aws_security_group.rds_sg.id]

  tags = {
    Project = "classicmodels-task1"
    Owner   = "grupo6-joao-vilas"
  }
}