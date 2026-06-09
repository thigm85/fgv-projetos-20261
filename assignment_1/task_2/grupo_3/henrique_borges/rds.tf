# --- Security Group do RDS ---

resource "aws_security_group" "rds" {
  name        = "rds-classicmodels-sg"
  description = "RDS MySQL - acesso restrito ao IP do provisionador e ao Glue"
  vpc_id      = data.aws_vpc.default.id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "rds-classicmodels-sg" }
}

# Acesso da máquina local via /32 (gap 2: sem 0.0.0.0/0)
resource "aws_security_group_rule" "rds_ingress_myip" {
  type              = "ingress"
  from_port         = 3306
  to_port           = 3306
  protocol          = "tcp"
  cidr_blocks       = [local.my_cidr]
  description       = "MySQL from provisioner IP only"
  security_group_id = aws_security_group.rds.id
}

# Acesso do Glue job ao RDS
resource "aws_security_group_rule" "rds_ingress_glue" {
  type                     = "ingress"
  from_port                = 3306
  to_port                  = 3306
  protocol                 = "tcp"
  source_security_group_id = aws_security_group.glue.id
  description              = "MySQL from Glue ETL job"
  security_group_id        = aws_security_group.rds.id
}

# --- RDS MySQL ---

resource "aws_db_instance" "classicmodels" {
  identifier        = var.rds_instance_id
  engine            = "mysql"
  engine_version    = "8.0"
  instance_class    = "db.t3.micro"
  allocated_storage = 20

  # db_name omitido: o banco classicmodels é criado pelo mysqlsampledatabase.sql
  username = var.rds_admin_user
  password = var.rds_admin_password

  publicly_accessible    = true
  vpc_security_group_ids = [aws_security_group.rds.id]

  skip_final_snapshot     = true
  deletion_protection     = false
  backup_retention_period = 0
  apply_immediately       = true

  tags = { Name = var.rds_instance_id }
}
