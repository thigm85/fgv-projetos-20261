provider "aws" {
  region = var.aws_region
}

# 1. Bucket S3 para Scripts e Dados (Gold Layer)
resource "aws_s3_bucket" "etl_bucket" {
  bucket_prefix = "fgv-etl-classicmodels-"
  force_destroy = true
}

# Upload do script de ETL
resource "aws_s3_object" "glue_script" {
  bucket = aws_s3_bucket.etl_bucket.id
  key    = "scripts/glue_job.py"
  source = "${path.module}/../etl/glue_job.py"
  etag   = filemd5("${path.module}/../etl/glue_job.py")
}

# 2. Security Group para o Glue
resource "aws_security_group" "glue_sg" {
  name_prefix = "glue-etl-sg-"
  description = "Allow Glue to communicate with RDS and S3 (via VPC Endpoints if applicable)"
  vpc_id      = var.vpc_id

  # Regra de Auto-referência (Obrigatória para Glue Connections)
  ingress {
    from_port = 0
    to_port   = 0
    protocol  = "-1"
    self      = true
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# Permissão no SG do RDS para aceitar conexões do SG do Glue
resource "aws_security_group_rule" "allow_glue_to_rds" {
  type                     = "ingress"
  from_port                = 3306
  to_port                  = 3306
  protocol                 = "tcp"
  security_group_id        = var.rds_sg_id # SG que está atrelado ao seu banco RDS
  source_security_group_id = aws_security_group.glue_sg.id
}

# 3. IAM Role (Usando Data para buscar existente ou criar uma nova)
data "aws_iam_role" "glue_role" {
  name = "LabRole" # Certifique-se que este nome existe no console AWS
}

# 4. Dados de Rede
data "aws_subnet" "selected" {
  id = var.subnet_id
}

# 5. Glue Connection (ESSENCIAL para acessar RDS na VPC)
resource "aws_glue_connection" "mysql_conn" {
  name = "classicmodels-mysql-conn"

  connection_properties = {
    JDBC_CONNECTION_URL = "jdbc:mysql://${var.db_host}:${var.db_port}/${var.db_name}"
    PASSWORD            = var.db_password
    USERNAME            = var.db_user
  }

  physical_connection_requirements {
    availability_zone      = data.aws_subnet.selected.availability_zone
    security_group_id_list = [aws_security_group.glue_sg.id]
    subnet_id              = var.subnet_id
  }
}

# 5.1 VPC Endpoint para S3 (Obrigatório para Glue acessar S3 via Rede Privada)
resource "aws_vpc_endpoint" "s3" {
  vpc_id       = var.vpc_id
  service_name = "com.amazonaws.${var.aws_region}.s3"
  route_table_ids = [data.aws_route_table.selected.id]
}

data "aws_route_table" "selected" {
  vpc_id = var.vpc_id
  filter {
    name   = "association.main"
    values = ["true"]
  }
}

# 6. Glue Job
resource "aws_glue_job" "etl_job" {
  name              = "classicmodels-etl-job"
  role_arn          = data.aws_iam_role.glue_role.arn
  glue_version      = "4.0"
  worker_type       = "G.1X"
  number_of_workers = 2

  command {
    script_location = "s3://${aws_s3_bucket.etl_bucket.id}/${aws_s3_object.glue_script.key}"
    python_version  = "3"
  }

  # Conecta o Job à rede e às credenciais do banco
  connections = [aws_glue_connection.mysql_conn.name]

  default_arguments = {
    "--connection_name"      = aws_glue_connection.mysql_conn.name
    "--s3_output_path"       = "s3://${aws_s3_bucket.etl_bucket.id}/gold/"
    "--db_name"              = var.db_name
    "--job-language"         = "python"
    "--continuous-log-logGroup"          = "/aws-glue/jobs/logs-v2/"
    "--enable-continuous-cloudwatch-log" = "true"
  }
}

# 7. Glue Catalog e Crawler
resource "aws_glue_catalog_database" "classicmodels_gold" {
  name = "classicmodels_gold"
}

resource "aws_glue_crawler" "gold_crawler" {
  database_name = aws_glue_catalog_database.classicmodels_gold.name
  name          = "classicmodels-gold-crawler"
  role          = data.aws_iam_role.glue_role.arn

  s3_target {
    path = "s3://${aws_s3_bucket.etl_bucket.id}/gold/"
  }

  # Garante que o crawler só rode após o bucket e os dados existirem
  depends_on = [aws_s3_bucket.etl_bucket]
}
