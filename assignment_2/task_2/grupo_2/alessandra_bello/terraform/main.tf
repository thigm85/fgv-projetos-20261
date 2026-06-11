terraform {
  required_version = ">= 1.5"
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

###############################################################################
# Variáveis
###############################################################################

variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "project_prefix" {
  description = "Prefixo usado em todos os recursos"
  type        = string
  default     = "classicmodels"
}

variable "glue_job_name" {
  description = "Nome do Glue Job incremental (deve existir)"
  type        = string
  default     = "classicmodels-incremental-etl"
}

variable "s3_bucket" {
  description = "Bucket S3 para scripts e dados do pipeline"
  type        = string
}

variable "s3_scripts_prefix" {
  description = "Prefixo dentro do bucket para scripts Glue"
  type        = string
  default     = "glue-scripts"
}

variable "jdbc_url" {
  description = "JDBC URL do banco RDS classicmodels"
  type        = string
  sensitive   = true
}

variable "db_user" {
  description = "Usuário do banco"
  type        = string
  sensitive   = true
}

variable "db_password" {
  description = "Senha do banco"
  type        = string
  sensitive   = true
}

variable "glue_role_arn" {
  description = "ARN da IAM Role usada pelo Glue Job (ex: LabRole)"
  type        = string
}

variable "pipeline_name" {
  description = "Nome do pipeline no etl_watermark"
  type        = string
  default     = "classicmodels_sales"
}

variable "cron_schedule" {
  description = "Expressão cron para o EventBridge (UTC)"
  type        = string
  default     = "cron(0 12 ? * MON *)"  # semanal, segunda-feira, 12h UTC
}

###############################################################################
# Script do Glue Job no S3
###############################################################################

resource "aws_s3_object" "glue_script" {
  bucket = var.s3_bucket
  key    = "${var.s3_scripts_prefix}/incremental_etl.py"
  source = "${path.module}/../glue_jobs/incremental_etl.py"
  etag   = filemd5("${path.module}/../glue_jobs/incremental_etl.py")
}

###############################################################################
# Glue Job
###############################################################################

resource "aws_glue_job" "incremental_etl" {
  name         = var.glue_job_name
  role_arn     = var.glue_role_arn
  glue_version = "4.0"

  command {
    name            = "glueetl"
    script_location = "s3://${var.s3_bucket}/${aws_s3_object.glue_script.key}"
    python_version  = "3"
  }

  default_arguments = {
    "--job-language"                     = "python"
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-glue-datacatalog"          = "true"
    "--jdbc_url"                         = var.jdbc_url
    "--db_user"                          = var.db_user
    "--db_password"                      = var.db_password
    "--s3_output_path"                   = "s3://${var.s3_bucket}/analytics"
    "--pipeline_name"                    = var.pipeline_name
    "--TempDir"                          = "s3://${var.s3_bucket}/glue-temp/"
  }

  number_of_workers = 2
  worker_type       = "G.1X"
  timeout           = 60  # minutos

  tags = {
    Project = var.project_prefix
    Task    = "assignment2-task2"
  }
}

###############################################################################
# Catálogo Glue — fact_orders particionado
###############################################################################

resource "aws_glue_catalog_database" "analytics" {
  name = "${var.project_prefix}_analytics"
}

resource "aws_glue_catalog_table" "fact_orders" {
  name          = "fact_orders"
  database_name = aws_glue_catalog_database.analytics.name

  table_type = "EXTERNAL_TABLE"

  parameters = {
    "classification"        = "parquet"
    "parquet.compression"   = "SNAPPY"
    "EXTERNAL"              = "TRUE"
  }

  storage_descriptor {
    location      = "s3://${var.s3_bucket}/analytics/fact_orders/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"

    ser_de_info {
      name                  = "ParquetHiveSerDe"
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
      parameters = {
        "serialization.format" = "1"
      }
    }

    columns {
      name = "order_id"
      type = "int"
    }
    columns {
      name = "product_id"
      type = "string"
    }
    columns {
      name = "customer_id"
      type = "int"
    }
    columns {
      name = "office_id"
      type = "string"
    }
    columns {
      name = "order_date"
      type = "date"
    }
    columns {
      name = "order_status"
      type = "string"
    }
    columns {
      name = "quantity_ordered"
      type = "int"
    }
    columns {
      name = "price_each"
      type = "double"
    }
    columns {
      name = "sales_amount"
      type = "double"
    }
  }

  partition_keys {
    name = "order_year"
    type = "int"
  }

  partition_keys {
    name = "order_month"
    type = "int"
  }
}

###############################################################################
# IAM — Role do EventBridge para invocar Glue
###############################################################################

data "aws_iam_policy_document" "eventbridge_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["events.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "eventbridge_glue_role" {
  name               = "${var.project_prefix}-eventbridge-glue-role"
  assume_role_policy = data.aws_iam_policy_document.eventbridge_assume_role.json

  tags = {
    Project = var.project_prefix
  }
}

data "aws_iam_policy_document" "eventbridge_glue_policy" {
  statement {
    effect    = "Allow"
    actions   = ["glue:StartJobRun"]
    resources = [aws_glue_job.incremental_etl.arn]
  }
}

resource "aws_iam_role_policy" "eventbridge_glue_inline" {
  name   = "AllowStartGlueJob"
  role   = aws_iam_role.eventbridge_glue_role.id
  policy = data.aws_iam_policy_document.eventbridge_glue_policy.json
}

###############################################################################
# EventBridge — Regra cron
###############################################################################

resource "aws_cloudwatch_event_rule" "weekly_etl" {
  name                = "${var.project_prefix}-weekly-incremental-etl"
  description         = "Disparo semanal do Glue Job incremental classicmodels"
  schedule_expression = var.cron_schedule
  state               = "ENABLED"

  tags = {
    Project = var.project_prefix
  }
}

###############################################################################
# EventBridge — Target (dispara o Glue Job)
###############################################################################

resource "aws_cloudwatch_event_target" "glue_job_target" {
  rule      = aws_cloudwatch_event_rule.weekly_etl.name
  target_id = "classicmodels-incremental-glue-job"
  arn       = "arn:aws:glue:${var.aws_region}:${data.aws_caller_identity.current.account_id}:job/${aws_glue_job.incremental_etl.name}"
  role_arn  = aws_iam_role.eventbridge_glue_role.arn

  input = jsonencode({
    Arguments = {
      "--pipeline_name" = var.pipeline_name
    }
  })
}

data "aws_caller_identity" "current" {}

###############################################################################
# Outputs
###############################################################################

output "glue_job_name" {
  value = aws_glue_job.incremental_etl.name
}

output "glue_job_arn" {
  value = aws_glue_job.incremental_etl.arn
}

output "eventbridge_rule_name" {
  value = aws_cloudwatch_event_rule.weekly_etl.name
}

output "eventbridge_role_arn" {
  value = aws_iam_role.eventbridge_glue_role.arn
}

output "glue_catalog_table" {
  value = "${aws_glue_catalog_database.analytics.name}.${aws_glue_catalog_table.fact_orders.name}"
}
