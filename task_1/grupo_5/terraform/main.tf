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

data "aws_caller_identity" "current" {}

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
  description       = "MySQL a partir do CIDR ${each.value}"
  ip_protocol       = "tcp"
  from_port         = 3306
  to_port           = 3306
  cidr_ipv4         = each.value
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

resource "aws_security_group" "glue_etl" {
  name_prefix = "${var.db_identifier}-glue-etl-"
  description = "Glue ETL security group (somente egress; usado para acesso ao RDS via regra referenciada)"
  vpc_id      = data.aws_db_subnet_group.this.vpc_id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_vpc_security_group_ingress_rule" "glue_self_tcp" {
  security_group_id            = aws_security_group.glue_etl.id
  description                  = "Glue VPC self TCP (workers)"
  ip_protocol                  = "tcp"
  from_port                    = 0
  to_port                      = 65535
  referenced_security_group_id = aws_security_group.glue_etl.id
}

resource "aws_vpc_security_group_ingress_rule" "mysql_from_glue_sg" {
  security_group_id            = aws_security_group.rds_mysql.id
  description                  = "MySQL a partir do SG do Glue ETL"
  ip_protocol                  = "tcp"
  from_port                    = 3306
  to_port                      = 3306
  referenced_security_group_id = aws_security_group.glue_etl.id
}

resource "aws_s3_bucket" "task2_curated" {
  bucket_prefix = "${var.project_name}-task2-"
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "task2_curated" {
  bucket                  = aws_s3_bucket.task2_curated.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

locals {
  # No AWS Academy Learner Lab geralmente não é permitido iam:CreateRole/AttachRolePolicy.
  # Portanto, usamos uma role EXISTENTE informada via variável.
  glue_role_arn = var.glue_role_arn
}

resource "aws_s3_object" "glue_script" {
  bucket = aws_s3_bucket.task2_curated.id
  key    = "glue/scripts/glue_etl_star_schema.py"
  source = "${path.module}/../../../../task_2/grupo_5/gabriel_rodrigues/glue_etl_star_schema.py"
  etag   = filemd5("${path.module}/../../../../task_2/grupo_5/gabriel_rodrigues/glue_etl_star_schema.py")
}

resource "aws_glue_connection" "rds_mysql" {
  name            = "${var.project_name}-${var.db_identifier}-rds-mysql"
  connection_type = "JDBC"

  connection_properties = {
    JDBC_CONNECTION_URL = "jdbc:mysql://${aws_db_instance.this.address}:${aws_db_instance.this.port}/classicmodels"
    USERNAME            = var.db_username
    PASSWORD            = var.db_password
    JDBC_ENFORCE_SSL    = "false"
  }

  physical_connection_requirements {
    subnet_id              = coalesce(var.glue_subnet_id, tolist(data.aws_db_subnet_group.this.subnet_ids)[0])
    security_group_id_list = [aws_security_group.glue_etl.id]
  }
}

resource "aws_glue_job" "etl_star_schema" {
  name     = "${var.project_name}-${var.db_identifier}-etl-star-schema"
  role_arn = local.glue_role_arn

  glue_version      = "4.0"
  worker_type       = "G.1X"
  number_of_workers = 2

  connections = [aws_glue_connection.rds_mysql.name]

  command {
    name            = "glueetl"
    python_version  = "3"
    script_location = "s3://${aws_s3_bucket.task2_curated.bucket}/${aws_s3_object.glue_script.key}"
  }

  default_arguments = {
    "--job-language"                     = "python"
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-metrics"                   = "true"
    "--GLUE_CONNECTION_NAME"             = aws_glue_connection.rds_mysql.name
    "--S3_OUTPUT_BASE"                   = "s3://${aws_s3_bucket.task2_curated.bucket}/curated"
  }
}

resource "aws_db_instance" "this" {
  identifier     = var.db_identifier
  engine         = "mysql"
  engine_version = "5.7"
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
