terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    local = {
      source  = "hashicorp/local"
      version = "~> 2.4"
    }
  }
}

#==========================
# Credenciais e região
#==========================

provider "aws" {
  region  = "us-east-1"
  profile = "projetos"
}

#==========================
# Variáveis (valores em terraform.tfvars)
#==========================

variable "senha_master" {
  type        = string
  description = "Senha do usuário admin do MySQL. Não use @, / nem aspas (regra do RDS)."
  sensitive   = true
}

variable "meu_ip" {
  type        = string
  description = "Seu IP público para liberar a porta 3306 (só você). Ex: 203.0.113.44 — use curl -s https://checkip.amazonaws.com"
}

variable "s3_bucket_name" {
  type        = string
  description = "S3 bucket name to store Glue outputs (must be globally unique)"
}

variable "glue_job_name" {
  type        = string
  description = "Name for the Glue job"
  default     = "classicmodels-etl-job"
}

#==========================
# VPC e subnets (default da conta)
#==========================

data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

data "aws_subnet" "glue" {
  id = sort(data.aws_subnets.default.ids)[0]
}

resource "aws_db_subnet_group" "lab" {
  name       = "lab-mysql-subnets"
  subnet_ids = data.aws_subnets.default.ids
}

#==========================
# Firewall RDS — só meu IP na 3306
#==========================

resource "aws_security_group" "mysql" {
  name        = "lab-mysql-sg"
  description = "Libera MySQL (3306) so para o meu IP"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    from_port   = 3306
    to_port     = 3306
    protocol    = "tcp"
    cidr_blocks = ["${var.meu_ip}/32"]
  }
}

#==========================
# Instância RDS MySQL
#==========================

resource "aws_db_instance" "mysql" {
  identifier = "lab-mysql-classicmodels"

  engine            = "mysql"
  engine_version    = "8.4.7"
  instance_class    = "db.t3.micro"
  allocated_storage = 20
  storage_type      = "gp3"

  username = "admin"
  password = var.senha_master

  db_subnet_group_name   = aws_db_subnet_group.lab.name
  vpc_security_group_ids = [aws_security_group.mysql.id]

  publicly_accessible = true

  skip_final_snapshot = true
}

# ==========================
# S3 bucket para outputs do Glue
# ==========================

resource "aws_s3_bucket" "data" {
  bucket = var.s3_bucket_name
}

# ==========================
# IAM — usa LabRole da conta via caller identity (nao criamos pq o lab nao deixa)
# ==========================

data "aws_caller_identity" "current" {}

locals {
  glue_role_arn = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/LabRole"
}

# ==========================
# VPC Endpoint para S3 (exigido pelo Glue em subnet sem NAT)
# ==========================

data "aws_route_table" "default" {
  vpc_id = data.aws_vpc.default.id
  filter {
    name   = "association.main"
    values = ["true"]
  }
}

resource "aws_vpc_endpoint" "s3" {
  vpc_id          = data.aws_vpc.default.id
  service_name    = "com.amazonaws.us-east-1.s3"
  route_table_ids = [data.aws_route_table.default.id]
}

# ==========================
# Security group para o Glue (self-reference + acesso ao RDS)
# ==========================

resource "aws_security_group" "glue" {
  name        = "lab-glue-sg"
  description = "Security group for Glue ENIs"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    from_port = 0
    to_port   = 65535
    protocol  = "tcp"
    self      = true
  }

  egress {
    from_port = 0
    to_port   = 0
    protocol  = "-1"
    self      = true
  }
}

resource "aws_security_group_rule" "allow_mysql_from_glue" {
  type                     = "ingress"
  from_port                = 3306
  to_port                  = 3306
  protocol                 = "tcp"
  security_group_id        = aws_security_group.mysql.id
  source_security_group_id = aws_security_group.glue.id
  description              = "Allow MySQL access from Glue"
}

# ==========================
# Secrets Manager (credenciais do RDS)
# ==========================

resource "aws_secretsmanager_secret" "db_secret" {
  name = "classicmodels-db-secret-gt"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "db_secret_version" {
  secret_id     = aws_secretsmanager_secret.db_secret.id
  secret_string = jsonencode({
    username = "admin",
    password = var.senha_master,
    host     = aws_db_instance.mysql.address,
    port     = aws_db_instance.mysql.port,
    dbname   = "classicmodels"
  })
}

# ==========================
# Glue connection e job
# ==========================

resource "aws_glue_connection" "rds_conn" {
  name = "classicmodels-jdbc-conn"
  connection_type = "JDBC"

  connection_properties = {
    JDBC_CONNECTION_URL = "jdbc:mysql://${aws_db_instance.mysql.address}:${aws_db_instance.mysql.port}/classicmodels"
    SECRET_ID           = aws_secretsmanager_secret.db_secret.name
  }

  physical_connection_requirements {
    availability_zone      = data.aws_subnet.glue.availability_zone
    subnet_id              = sort(data.aws_subnets.default.ids)[0]
    security_group_id_list = [aws_security_group.glue.id]
  }
}

# Upload ETL script to S3
resource "aws_s3_object" "glue_script" {
  bucket = aws_s3_bucket.data.id
  key    = "scripts/glue_job_main.py"
  source = "${path.module}/../glue/glue_job_main.py"
  etag   = filemd5("${path.module}/../glue/glue_job_main.py")
}

resource "aws_glue_job" "etl" {
  name     = var.glue_job_name
  role_arn = local.glue_role_arn

  glue_version    = "4.0"
  number_of_workers = 2
  worker_type     = "G.1X"

  command {
    name         = "glueetl"
    python_version = "3"
    script_location = "s3://${aws_s3_bucket.data.bucket}/scripts/glue_job_main.py"
  }

  connections = [aws_glue_connection.rds_conn.name]

  default_arguments = {
    "--TempDir"                          = "s3://${aws_s3_bucket.data.bucket}/tmp/"
    "--SECRET_ARN"                       = aws_secretsmanager_secret.db_secret.arn
    "--S3_BUCKET"                        = aws_s3_bucket.data.bucket
    "--job-language"                     = "python"
    "--enable-continuous-cloudwatch-log" = "true"
  }

  depends_on = [aws_s3_object.glue_script]
}


#==========================
# Saídas no terminal após apply (terraform output)
#==========================

output "endpoint" {
  description = "Host RDS"
  value       = aws_db_instance.mysql.address
}

output "porta" {
  value = aws_db_instance.mysql.port
}

output "usuario" {
  value = "admin"
}

output "secret_arn" {
  value = aws_secretsmanager_secret.db_secret.arn
}

#==========================
# Grava src/.env
#==========================

resource "local_file" "env" {
  filename        = "${path.module}/../src/.env"
  file_permission = "0600"
  content         = "SECRET_ARN=${aws_secretsmanager_secret.db_secret.arn}\nS3_BUCKET=${aws_s3_bucket.data.bucket}\nGLUE_JOB_NAME=${var.glue_job_name}\n"
}
