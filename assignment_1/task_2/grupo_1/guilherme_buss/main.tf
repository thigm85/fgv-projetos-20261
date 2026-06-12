terraform {
  required_version = ">= 1.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
  backend "local" {
    path = "terraform.tfstate"
  }
}

provider "aws" {
  region  = var.aws_region
  profile = var.aws_profile
  default_tags {
    tags = var.tags
  }
}

data "aws_caller_identity" "current" {}

resource "aws_security_group" "rds_sg" {
  name        = "${var.project_name}-rds-sg"
  description = "RDS security group"
  ingress {
    from_port   = 3306
    to_port     = 3306
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_db_parameter_group" "classic_models_params" {
  family = "mysql8.0"
  name   = "${var.project_name}-params"
  parameter {
    name  = "character_set_server"
    value = "utf8mb4"
  }
  parameter {
    name  = "collation_server"
    value = "utf8mb4_unicode_ci"
  }
}

resource "aws_db_instance" "classic_models_db" {
  identifier              = var.rds_instance_identifier
  engine                  = "mysql"
  engine_version          = var.rds_engine_version
  instance_class          = var.rds_instance_class
  allocated_storage       = var.rds_allocated_storage
  storage_type            = "gp2"
  storage_encrypted       = true
  db_name                 = var.db_name
  username                = var.db_master_username
  password                = var.db_master_password
  publicly_accessible     = var.enable_rds_public_access
  skip_final_snapshot     = true
  multi_az                = false
  backup_retention_period = 7
  vpc_security_group_ids  = [aws_security_group.rds_sg.id]
  enabled_cloudwatch_logs_exports = ["error", "general", "slowquery"]
  parameter_group_name    = aws_db_parameter_group.classic_models_params.name
}

resource "aws_s3_bucket" "etl_output" {
  bucket = var.s3_bucket_name != "" ? var.s3_bucket_name : "${var.project_name}-etl-output-${data.aws_caller_identity.current.account_id}"
}

resource "aws_s3_bucket_versioning" "etl_output" {
  bucket = aws_s3_bucket.etl_output.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "etl_output" {
  bucket = aws_s3_bucket.etl_output.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "etl_output" {
  bucket                  = aws_s3_bucket.etl_output.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_cloudwatch_log_group" "glue_job_logs" {
  name              = "/aws/glue/${var.glue_job_name}"
  retention_in_days = 14
}

resource "aws_secretsmanager_secret" "rds_credentials" {
  name                    = "${var.project_name}/rds-credentials"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "rds_credentials" {
  secret_id = aws_secretsmanager_secret.rds_credentials.id
  secret_string = jsonencode({
    username = var.db_master_username
    password = var.db_master_password
  })
}

data "aws_iam_role" "lab_role" {
  name = "LabRole"
}

resource "aws_glue_connection" "rds_jdbc" {
  name            = "${var.project_name}-rds-connection"
  connection_type = "JDBC"
  connection_properties = {
    SECRET_ID           = aws_secretsmanager_secret.rds_credentials.id
    JDBC_CONNECTION_URL = "jdbc:mysql://${aws_db_instance.classic_models_db.endpoint}/${var.db_name}?useSSL=false&serverTimezone=UTC"
  }
}

resource "aws_s3_object" "glue_script" {
  bucket = aws_s3_bucket.etl_output.id
  key    = "glue-scripts/etl_script.py"
  source = "${path.module}/glue_etl_script.py"
  etag   = filemd5("${path.module}/glue_etl_script.py")
}

resource "aws_glue_job" "classic_models_etl" {
  name     = var.glue_job_name
  role_arn = data.aws_iam_role.lab_role.arn
  command {
    name            = "glueetl"
    script_location = "s3://${aws_s3_bucket.etl_output.id}/${aws_s3_object.glue_script.key}"
    python_version  = "3"
  }

  default_arguments = {
    "--job-bookmark-option"     = "job-bookmark-enable"
    "--TempDir"                 = "s3://${aws_s3_bucket.etl_output.id}/temp/"
    "--enable-spark-ui"         = "true"
    "--spark-event-logs-path"   = "s3://${aws_s3_bucket.etl_output.id}/spark-logs/"
    "--CONNECTION_NAME"         = aws_glue_connection.rds_jdbc.name
    "--JDBC_URL"                = "jdbc:mysql://${aws_db_instance.classic_models_db.endpoint}/${var.db_name}?useSSL=false&serverTimezone=UTC"
    "--DATABASE_NAME"           = var.db_name
    "--S3_OUTPUT_PATH"          = "s3://${aws_s3_bucket.etl_output.id}/output/"
    "--RDS_SECRET_ARN"          = aws_secretsmanager_secret.rds_credentials.arn
    "--AWS_REGION"              = var.aws_region
  }

  max_retries   = 1
  timeout       = 2880
  glue_version  = "4.0"
  worker_type   = var.glue_job_worker_type
  number_of_workers = var.glue_job_num_workers
  execution_property {
    max_concurrent_runs = 1
  }

  depends_on = [aws_glue_connection.rds_jdbc, aws_s3_object.glue_script]
}

output "rds_endpoint" {
  value = aws_db_instance.classic_models_db.endpoint
}

output "rds_address" {
  value = aws_db_instance.classic_models_db.address
}

output "rds_port" {
  value = aws_db_instance.classic_models_db.port
}

output "database_name" {
  value = aws_db_instance.classic_models_db.db_name
}

output "database_master_username" {
  value = aws_db_instance.classic_models_db.username
}

output "s3_bucket_name" {
  value = aws_s3_bucket.etl_output.id
}

output "glue_job_name" {
  value = aws_glue_job.classic_models_etl.name
}

output "iam_role_arn" { 
  value = data.aws_iam_role.lab_role.arn
}