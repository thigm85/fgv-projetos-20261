# ============================================================================
# Assignment 2 — Task 2: Incremental ETL Infrastructure
# ============================================================================
# This module creates:
#   - A new Glue job for incremental ETL
#   - Glue Catalog database + tables (with partitions for fact_orders)
#   - EventBridge rule + target for scheduled execution
#   - IAM policy for EventBridge → Glue
# ============================================================================

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

# ---------------------------------------------------------------------------
# Data sources — reference existing A1 resources
# ---------------------------------------------------------------------------

data "aws_caller_identity" "current" {}

data "aws_iam_role" "lab_role" {
  name = "LabRole"
}

data "aws_s3_bucket" "etl_output" {
  bucket = var.s3_bucket_name
}

data "aws_secretsmanager_secret" "rds_credentials" {
  name = var.rds_secret_name
}

# ---------------------------------------------------------------------------
# Upload Glue script to S3
# ---------------------------------------------------------------------------

resource "aws_s3_object" "incremental_glue_script" {
  bucket = data.aws_s3_bucket.etl_output.id
  key    = "glue-scripts/incremental_etl_script.py"
  source = "${path.module}/../glue_incremental_etl.py"
  etag   = filemd5("${path.module}/../glue_incremental_etl.py")
}

# ---------------------------------------------------------------------------
# Glue Job — Incremental ETL
# ---------------------------------------------------------------------------

resource "aws_glue_job" "incremental_etl" {
  name     = var.glue_job_name
  role_arn = data.aws_iam_role.lab_role.arn

  connections = [var.glue_connection_name]

  command {
    name            = "glueetl"
    script_location = "s3://${data.aws_s3_bucket.etl_output.id}/${aws_s3_object.incremental_glue_script.key}"
    python_version  = "3"
  }

  default_arguments = {
    "--job-bookmark-option"   = "job-bookmark-disable"
    "--TempDir"               = "s3://${data.aws_s3_bucket.etl_output.id}/temp/"
    "--enable-spark-ui"       = "true"
    "--spark-event-logs-path" = "s3://${data.aws_s3_bucket.etl_output.id}/spark-logs/"
    "--CONNECTION_NAME"       = var.glue_connection_name
    "--JDBC_URL"              = "jdbc:mysql://${var.rds_endpoint}/${var.db_name}?useSSL=false&serverTimezone=UTC"
    "--DATABASE_NAME"         = var.db_name
    "--S3_OUTPUT_PATH"        = "s3://${data.aws_s3_bucket.etl_output.id}/${var.s3_output_prefix}"
    "--RDS_SECRET_ARN"        = data.aws_secretsmanager_secret.rds_credentials.arn
    "--AWS_REGION"            = var.aws_region
  }

  max_retries       = 1
  timeout           = 2880
  glue_version      = "4.0"
  worker_type       = var.glue_worker_type
  number_of_workers = var.glue_num_workers

  execution_property {
    max_concurrent_runs = 1
  }

  depends_on = [aws_s3_object.incremental_glue_script]
}

# ---------------------------------------------------------------------------
# Glue Catalog — Database
# ---------------------------------------------------------------------------

resource "aws_glue_catalog_database" "analytics" {
  name = var.glue_catalog_database
}

# ---------------------------------------------------------------------------
# Glue Catalog — fact_orders (partitioned by order_year, order_month)
# ---------------------------------------------------------------------------

resource "aws_glue_catalog_table" "fact_orders" {
  database_name = aws_glue_catalog_database.analytics.name
  name          = "fact_orders"

  table_type = "EXTERNAL_TABLE"

  parameters = {
    "classification" = "parquet"
    "EXTERNAL"       = "TRUE"
  }

  storage_descriptor {
    location      = "s3://${data.aws_s3_bucket.etl_output.id}/${var.s3_output_prefix}fact_orders/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"

    ser_de_info {
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
      name = "customer_id"
      type = "int"
    }
    columns {
      name = "product_id"
      type = "string"
    }
    columns {
      name = "order_date_key"
      type = "int"
    }
    columns {
      name = "country_key"
      type = "int"
    }
    columns {
      name = "quantity_ordered"
      type = "int"
    }
    columns {
      name = "price_each"
      type = "decimal(10,2)"
    }
    columns {
      name = "sales_amount"
      type = "decimal(12,2)"
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

# ---------------------------------------------------------------------------
# Glue Catalog — dim_customers
# ---------------------------------------------------------------------------

resource "aws_glue_catalog_table" "dim_customers" {
  database_name = aws_glue_catalog_database.analytics.name
  name          = "dim_customers"
  table_type    = "EXTERNAL_TABLE"

  parameters = {
    "classification" = "parquet"
    "EXTERNAL"       = "TRUE"
  }

  storage_descriptor {
    location      = "s3://${data.aws_s3_bucket.etl_output.id}/${var.s3_output_prefix}dim_customers/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"

    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
      parameters = {
        "serialization.format" = "1"
      }
    }

    columns {
      name = "customer_id"
      type = "int"
    }
    columns {
      name = "customer_name"
      type = "string"
    }
    columns {
      name = "contact_name"
      type = "string"
    }
    columns {
      name = "city"
      type = "string"
    }
    columns {
      name = "country"
      type = "string"
    }
  }
}

# ---------------------------------------------------------------------------
# Glue Catalog — dim_products
# ---------------------------------------------------------------------------

resource "aws_glue_catalog_table" "dim_products" {
  database_name = aws_glue_catalog_database.analytics.name
  name          = "dim_products"
  table_type    = "EXTERNAL_TABLE"

  parameters = {
    "classification" = "parquet"
    "EXTERNAL"       = "TRUE"
  }

  storage_descriptor {
    location      = "s3://${data.aws_s3_bucket.etl_output.id}/${var.s3_output_prefix}dim_products/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"

    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
      parameters = {
        "serialization.format" = "1"
      }
    }

    columns {
      name = "product_id"
      type = "string"
    }
    columns {
      name = "product_name"
      type = "string"
    }
    columns {
      name = "product_line"
      type = "string"
    }
    columns {
      name = "product_vendor"
      type = "string"
    }
  }
}

# ---------------------------------------------------------------------------
# Glue Catalog — dim_dates
# ---------------------------------------------------------------------------

resource "aws_glue_catalog_table" "dim_dates" {
  database_name = aws_glue_catalog_database.analytics.name
  name          = "dim_dates"
  table_type    = "EXTERNAL_TABLE"

  parameters = {
    "classification" = "parquet"
    "EXTERNAL"       = "TRUE"
  }

  storage_descriptor {
    location      = "s3://${data.aws_s3_bucket.etl_output.id}/${var.s3_output_prefix}dim_dates/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"

    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
      parameters = {
        "serialization.format" = "1"
      }
    }

    columns {
      name = "date_key"
      type = "int"
    }
    columns {
      name = "full_date"
      type = "date"
    }
    columns {
      name = "year"
      type = "int"
    }
    columns {
      name = "quarter"
      type = "int"
    }
    columns {
      name = "month"
      type = "int"
    }
    columns {
      name = "day"
      type = "int"
    }
  }
}

# ---------------------------------------------------------------------------
# Glue Catalog — dim_countries
# ---------------------------------------------------------------------------

resource "aws_glue_catalog_table" "dim_countries" {
  database_name = aws_glue_catalog_database.analytics.name
  name          = "dim_countries"
  table_type    = "EXTERNAL_TABLE"

  parameters = {
    "classification" = "parquet"
    "EXTERNAL"       = "TRUE"
  }

  storage_descriptor {
    location      = "s3://${data.aws_s3_bucket.etl_output.id}/${var.s3_output_prefix}dim_countries/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"

    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
      parameters = {
        "serialization.format" = "1"
      }
    }

    columns {
      name = "country_key"
      type = "int"
    }
    columns {
      name = "country"
      type = "string"
    }
    columns {
      name = "territory"
      type = "string"
    }
  }
}

# ---------------------------------------------------------------------------
# EventBridge — Scheduled rule (weekly, Monday at 12:00 UTC)
# ---------------------------------------------------------------------------

resource "aws_cloudwatch_event_rule" "glue_schedule" {
  name                = "${var.project_name}-incremental-etl-schedule"
  description         = "Weekly trigger for incremental Glue ETL job (Monday 12:00 UTC)"
  schedule_expression = var.schedule_expression
  state               = var.schedule_enabled ? "ENABLED" : "DISABLED"
}

resource "aws_cloudwatch_event_target" "glue_target" {
  rule      = aws_cloudwatch_event_rule.glue_schedule.name
  target_id = "GlueIncrementalETL"
  arn       = aws_glue_job.incremental_etl.arn
  role_arn  = data.aws_iam_role.lab_role.arn
}

# ---------------------------------------------------------------------------
# CloudWatch Log Group
# ---------------------------------------------------------------------------

resource "aws_cloudwatch_log_group" "incremental_glue_logs" {
  name              = "/aws/glue/${var.glue_job_name}"
  retention_in_days = 14
}

# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------

output "glue_job_name" {
  value = aws_glue_job.incremental_etl.name
}

output "glue_job_arn" {
  value = aws_glue_job.incremental_etl.arn
}

output "eventbridge_rule_name" {
  value = aws_cloudwatch_event_rule.glue_schedule.name
}

output "eventbridge_rule_arn" {
  value = aws_cloudwatch_event_rule.glue_schedule.arn
}

output "glue_catalog_database" {
  value = aws_glue_catalog_database.analytics.name
}

output "s3_fact_orders_path" {
  value = "s3://${data.aws_s3_bucket.etl_output.id}/${var.s3_output_prefix}fact_orders/"
}
