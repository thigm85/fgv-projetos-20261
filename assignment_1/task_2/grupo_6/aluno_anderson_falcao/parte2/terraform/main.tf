terraform {
  required_version = ">= 1.3.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.region
}

# -- Data Sources -----------------------------------------------------------------

data "aws_caller_identity" "current" {}

# VPC padrao - mesma VPC onde o RDS foi provisionado por 1_provision_rds.py
data "aws_vpc" "default" {
  default = true
}

# Subnet padrao na AZ "a" - Glue precisa de uma subnet especifica na conexao JDBC
data "aws_subnet" "glue_subnet" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
  filter {
    name   = "defaultForAz"
    values = ["true"]
  }
  filter {
    name   = "availabilityZone"
    values = ["${var.region}a"]
  }
}

# Security Group do RDS criado pelo script 1_provision_rds.py
data "aws_security_group" "rds_sg" {
  name   = "${var.project_name}-db-sg"
  vpc_id = data.aws_vpc.default.id
}

# Prefix list do S3 (IPs gerenciados pela AWS para o Gateway Endpoint)
data "aws_prefix_list" "s3" {
  name = "com.amazonaws.${var.region}.s3"
}

# -- S3 Bucket para output do ETL -------------------------------------------------

resource "aws_s3_bucket" "etl" {
  # Sufixo com account ID garante nome globalmente unico (idempotente)
  bucket        = "${var.project_name}-etl-${data.aws_caller_identity.current.account_id}"
  force_destroy = true

  tags = { Project = var.project_name }
}

resource "aws_s3_bucket_public_access_block" "etl" {
  bucket                  = aws_s3_bucket.etl.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Upload do script PySpark ao S3 - Glue le o script diretamente daqui
# O etag garante re-upload automatico sempre que o script mudar (idempotente)
resource "aws_s3_object" "glue_script" {
  bucket = aws_s3_bucket.etl.id
  key    = "scripts/2_glue_etl_job.py"
  source = "${path.module}/../scripts/2_glue_etl_job.py"
  etag   = filemd5("${path.module}/../scripts/2_glue_etl_job.py")
}

# -- VPC Gateway Endpoint para S3 -------------------------------------------------
# Permite que o Glue (dentro da VPC) acesse o S3 sem precisar de internet.
# Gateway endpoint e gratuito e melhora seguranca e latencia.
# Route table da subnet padrão (necessária para associar o Gateway Endpoint S3)

data "aws_route_table" "main" {
  vpc_id = data.aws_vpc.default.id
  filter {
    name   = "association.main"
    values = ["true"]
  }
}

resource "aws_vpc_endpoint" "s3" {
  vpc_id            = data.aws_vpc.default.id
  service_name      = "com.amazonaws.${var.region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [data.aws_route_table.main.id]  # NOVO

  tags = { Project = var.project_name }
}

# -- Security Group para o Glue ---------------------------------------------------
resource "aws_security_group" "glue" {
  name   = "${var.project_name}-glue-sg"
  vpc_id = data.aws_vpc.default.id

  # Self-referencing obrigatorio
  ingress {
    from_port = 0
    to_port   = 65535
    protocol  = "tcp"
    self      = true
  }

  # Ingress HTTPS para VPC Endpoints
  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = [data.aws_vpc.default.cidr_block]
  }

  # Egress self-referencing obrigatorio para workers Glue
  egress {
    description = "Self-referencing para coordenacao entre workers do cluster Glue"
    from_port   = 0
    to_port     = 65535
    protocol    = "tcp"
    self        = true
  }

  # Egress para RDS
  egress {
    from_port       = 3306
    to_port         = 3306
    protocol        = "tcp"
    security_groups = [data.aws_security_group.rds_sg.id]
  }

  # Egress HTTPS para APIs AWS dentro da VPC (Glue API, CloudWatch via Interface Endpoints)
  egress {
    description = "HTTPS para Interface Endpoints na VPC"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = [data.aws_vpc.default.cidr_block]
  }

  # Egress HTTPS para S3 via Gateway Endpoint (prefix list = least privilege)
  egress {
    description     = "HTTPS para S3 via Gateway Endpoint"
    from_port       = 443
    to_port         = 443
    protocol        = "tcp"
    prefix_list_ids = [data.aws_prefix_list.s3.id]
  }

  tags = { Project = var.project_name }
}

# VPC Endpoint: Glue API
resource "aws_vpc_endpoint" "glue_api" {
  vpc_id              = data.aws_vpc.default.id
  service_name        = "com.amazonaws.${var.region}.glue"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = [data.aws_subnet.glue_subnet.id]
  security_group_ids  = [aws_security_group.glue.id]
  private_dns_enabled = true

  tags = { Project = var.project_name }
}

# VPC Endpoint: CloudWatch Logs
resource "aws_vpc_endpoint" "cloudwatch_logs" {
  vpc_id              = data.aws_vpc.default.id
  service_name        = "com.amazonaws.${var.region}.logs"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = [data.aws_subnet.glue_subnet.id]
  security_group_ids  = [aws_security_group.glue.id]
  private_dns_enabled = true

  tags = { Project = var.project_name }
}

# Regra adicional no SG do RDS: permite conexao vinda do Glue
# Usa aws_security_group_rule separado pois o SG do RDS foi criado fora do Terraform
resource "aws_security_group_rule" "rds_allow_glue" {
  type                     = "ingress"
  description              = "Permite MySQL do Glue ETL Job"
  from_port                = 3306
  to_port                  = 3306
  protocol                 = "tcp"
  source_security_group_id = aws_security_group.glue.id
  security_group_id        = data.aws_security_group.rds_sg.id
}

# -- Glue Connection (JDBC -> MySQL no RDS) ----------------------------------------

resource "aws_glue_connection" "mysql" {
  name = "${var.project_name}-mysql-connection"

  connection_type = "JDBC"

  connection_properties = {
    JDBC_CONNECTION_URL = "jdbc:mysql://${var.rds_host}:${var.rds_port}/${var.db_name}?useSSL=false&serverTimezone=UTC"
    USERNAME            = var.db_username
    PASSWORD            = var.db_password
  }

  physical_connection_requirements {
    subnet_id              = data.aws_subnet.glue_subnet.id
    availability_zone      = data.aws_subnet.glue_subnet.availability_zone
    security_group_id_list = [aws_security_group.glue.id]
  }
}

# -- Glue Job ---------------------------------------------------------------------
# Usa LabRole pré-existente do AWS Academy

resource "aws_glue_job" "etl" {
  name = "${var.project_name}-etl-job"

  # LabRole: role padrão do AWS Academy com permissões para Glue, S3, RDS e CloudWatch
  role_arn = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/LabRole"

  command {
    name            = "glueetl"
    script_location = "s3://${aws_s3_bucket.etl.bucket}/scripts/2_glue_etl_job.py"
    python_version  = "3"
  }

  default_arguments = {
    "--job-language"                     = "python"
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-metrics"                   = "true"
    "--TempDir"                          = "s3://${aws_s3_bucket.etl.bucket}/tmp/"

    # Parâmetros de negócio passados como args (zero hardcode no script)
    "--S3_OUTPUT_PATH" = "s3://${aws_s3_bucket.etl.bucket}/data"
    "--RDS_HOST"       = var.rds_host
    "--RDS_PORT"       = tostring(var.rds_port)
    "--DB_NAME"        = var.db_name
    "--DB_USERNAME"    = var.db_username
    "--DB_PASSWORD"    = var.db_password
  }

  # Conexão que fornece o roteamento de rede VPC -> RDS
  connections = [aws_glue_connection.mysql.name]

  glue_version      = "4.0"
  worker_type       = var.glue_worker_type
  number_of_workers = var.glue_number_of_workers
  timeout           = var.glue_timeout_minutes

  tags = { Project = var.project_name }
}
