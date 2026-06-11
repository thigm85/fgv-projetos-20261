provider "aws" {
  region = "us-east-1"
}

# Pega o IP local
data "http" "myip" {
  url = "https://checkip.amazonaws.com"
}

locals {
  my_ip = "${chomp(data.http.myip.response_body)}/32"
}

data "aws_vpc" "default" { default = true }

resource "aws_security_group" "rds_sg" {
  name        = "classicmodels-sg"
  description = "Acesso Local e autorreferencia para ETL"
  vpc_id      = data.aws_vpc.default.id

  # Acesso somente pela porta 3306 para segurança
  ingress {
    from_port   = 3306
    to_port     = 3306
    protocol    = "tcp"
    cidr_blocks = [local.my_ip]
  }

  # Permite conexão com o Glue
  ingress {
    from_port = 0
    to_port   = 65535
    protocol  = "tcp"
    self      = true
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_db_instance" "mysql_rds" {
  identifier             = "classicmodels-instance"
  engine                 = "mysql"
  instance_class         = "db.t3.micro"
  allocated_storage      = 20
  username               = "admin"
  password               = var.db_password
  publicly_accessible    = true
  vpc_security_group_ids = [aws_security_group.rds_sg.id]
  skip_final_snapshot    = true
}

# Atualiza o endpoint automaticamente
resource "local_file" "endpoint_file" {
  content  = replace(aws_db_instance.mysql_rds.endpoint, ":3306", "")
  filename = "${path.module}/rds_endpoint.txt"
}