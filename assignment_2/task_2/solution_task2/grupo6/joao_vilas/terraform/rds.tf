resource "aws_security_group" "rds_sg" {
  name        = "${var.project_prefix}-rds-sg"
  description = "RDS MySQL: ingresso permitido apenas do Glue SG e do IP admin /32"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description = "MySQL apenas a partir do IP publico autorizado (admin local)"
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
}

resource "aws_security_group_rule" "rds_from_glue" {
  type                     = "ingress"
  description              = "Permite MySQL somente a partir do Glue SG"
  from_port                = 3306
  to_port                  = 3306
  protocol                 = "tcp"
  security_group_id        = aws_security_group.rds_sg.id
  source_security_group_id = aws_security_group.glue_sg.id
}

resource "aws_db_instance" "classicmodels_db" {
  identifier              = var.db_identifier
  allocated_storage       = var.rds_allocated_storage_gb
  engine                  = "mysql"
  engine_version          = "8.0"
  instance_class          = var.rds_instance_class
  username                = var.db_username
  password                = random_password.db_password.result
  parameter_group_name    = "default.mysql8.0"
  skip_final_snapshot     = true
  publicly_accessible     = true
  vpc_security_group_ids  = [aws_security_group.rds_sg.id]
  storage_encrypted       = true
  backup_retention_period = 0
  deletion_protection     = false
  apply_immediately       = true
}
