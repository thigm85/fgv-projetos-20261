provider "aws" {
  region = var.aws_region
}

data "http" "myip" {
  url = "https://ipv4.icanhazip.com"
}

resource "aws_security_group" "rds_sg" {
  name = "public security group"
  description = "Permite conexao MySQL vinda da internet"

  ingress {
    from_port   = 3306
    to_port     = 3306
    protocol    = "tcp"
    cidr_blocks = ["${chomp(data.http.myip.response_body)}/32"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# Instância RDS MySQL
resource "aws_db_instance" "mysql_source" {
  allocated_storage    = 10
  db_name              = var.db_name
  engine               = "mysql"
  engine_version       = "8.0"
  instance_class       = "db.t3.micro"
  username             = var.db_username
  password             = var.db_password
  parameter_group_name = "default.mysql8.0"

  skip_final_snapshot  = true
  publicly_accessible  = true
  vpc_security_group_ids = [aws_security_group.rds_sg.id]
  
  tags = {
    Name    = "RDS-MySQL-Source"
    Project = "Data-Engineering-Lifecycle"
  }
}