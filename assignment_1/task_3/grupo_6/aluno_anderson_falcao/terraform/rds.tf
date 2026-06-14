# -- Subnet Group e Security Group para o RDS ---------------------------------------

data "aws_subnets" "all" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

resource "aws_db_subnet_group" "main" {
  name       = "${var.project_name}-subnet-group"
  subnet_ids = data.aws_subnets.all.ids

  tags = { Project = var.project_name }
}

resource "aws_security_group" "rds_sg" {
  name        = "${var.project_name}-db-sg"
  description = "Acesso MySQL para o laboratorio classicmodels"
  vpc_id      = data.aws_vpc.default.id

  # Ingresso restrito ao IP público atual da máquina executando Terraform (/32)
  ingress {
    description = "MySQL lab - IP restrito atual"
    from_port   = 3306
    to_port     = 3306
    protocol    = "tcp"
    cidr_blocks = ["${chomp(data.http.myip.response_body)}/32"]
  }

  tags = { Project = var.project_name }
}

# -- Instancia RDS MySQL ----------------------------------------------------------

resource "aws_db_instance" "main" {
  identifier           = var.db_instance_id
  db_name              = var.db_name
  username             = var.db_username
  password             = var.db_password
  instance_class       = var.instance_class
  engine               = "mysql"
  engine_version       = "8.0"
  allocated_storage    = 20
  publicly_accessible  = true
  
  vpc_security_group_ids = [aws_security_group.rds_sg.id]
  db_subnet_group_name   = aws_db_subnet_group.main.name
  
  skip_final_snapshot    = true
  backup_retention_period = 0 # Sem backups automatizados (Lab)
  multi_az               = false

  tags = { Project = var.project_name }
}
