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

# --------------------------------------------------------------------------- #
# Networking — VPC padrão                                                      #
# --------------------------------------------------------------------------- #

data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

data "aws_iam_role" "lab_role" {
  name = "LabRole"
}

# --------------------------------------------------------------------------- #
# Security Group — permite MySQL 3306 de qualquer IP (lab)                     #
# --------------------------------------------------------------------------- #

resource "aws_security_group" "rds_sg" {
  name        = "classicmodels-rds-sg"
  description = "Allow MySQL from anywhere (lab)"
  vpc_id      = data.aws_vpc.default.id

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

# --------------------------------------------------------------------------- #
# RDS MySQL                                                                    #
# --------------------------------------------------------------------------- #

resource "aws_db_subnet_group" "default" {
  name       = "classicmodels-subnet-group"
  subnet_ids = data.aws_subnets.default.ids
}

resource "aws_db_instance" "mysql" {
  identifier             = "classicmodels-db"
  engine                 = "mysql"
  engine_version         = "8.0"
  instance_class         = "db.t3.micro"
  allocated_storage      = 20
  db_name                = var.db_name
  username               = var.db_username
  password               = var.db_password
  db_subnet_group_name   = aws_db_subnet_group.default.name
  vpc_security_group_ids = [aws_security_group.rds_sg.id]
  publicly_accessible    = true
  skip_final_snapshot    = true
  multi_az               = false
  backup_retention_period = 0

  tags = {
    Project = "classicmodels"
  }
}

# --------------------------------------------------------------------------- #
# S3 — bucket analytics                                                        #
# --------------------------------------------------------------------------- #

resource "aws_s3_bucket" "analytics" {
  bucket        = "${var.bucket_name_prefix}-${data.aws_caller_identity.current.account_id}"
  force_destroy = true

  tags = {
    Project = "classicmodels"
  }
}

data "aws_caller_identity" "current" {}

resource "aws_s3_bucket_versioning" "analytics" {
  bucket = aws_s3_bucket.analytics.id
  versioning_configuration {
    status = "Disabled"
  }
}

# Upload do script PySpark para o S3
resource "aws_s3_object" "glue_script" {
  bucket = aws_s3_bucket.analytics.id
  key    = "scripts/incremental_etl.py"
  source = "${path.module}/../glue/incremental_etl.py"
  etag   = filemd5("${path.module}/../glue/incremental_etl.py")
}

# --------------------------------------------------------------------------- #
# Glue — Database, Connection, Job                                             #
# --------------------------------------------------------------------------- #

resource "aws_glue_catalog_database" "analytics" {
  name = "classicmodels_analytics"
}

resource "aws_glue_job" "incremental_etl" {
  name         = var.glue_job_name
  role_arn     = data.aws_iam_role.lab_role.arn
  glue_version = "4.0"

  command {
    name            = "glueetl"
    script_location = "s3://${aws_s3_bucket.analytics.id}/scripts/incremental_etl.py"
    python_version  = "3"
  }

  default_arguments = {
    "--job-language"                     = "python"
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-metrics"                   = "true"
    "--S3_BUCKET"                        = aws_s3_bucket.analytics.id
    "--GLUE_DATABASE"                    = aws_glue_catalog_database.analytics.name
    "--DB_NAME"                          = var.db_name
    "--DB_HOST"                          = aws_db_instance.mysql.address
    "--DB_USER"                          = var.db_username
    "--DB_PASSWORD"                      = var.db_password
  }

  number_of_workers = 2
  worker_type       = "G.1X"
  timeout           = 60

  tags = {
    Project = "classicmodels"
  }
}

# --------------------------------------------------------------------------- #
# Glue Catalog — tabela fact_orders com partition keys                         #
# --------------------------------------------------------------------------- #

resource "aws_glue_catalog_table" "fact_orders" {
  name          = "fact_orders"
  database_name = aws_glue_catalog_database.analytics.name

  table_type = "EXTERNAL_TABLE"

  parameters = {
    "classification"  = "parquet"
    "EXTERNAL"        = "TRUE"
  }

  storage_descriptor {
    location      = "s3://${aws_s3_bucket.analytics.id}/analytics/fact_orders/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"

    ser_de_info {
      name                  = "parquet"
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
      type = "string"
    }
    columns {
      name = "country_key"
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

# --------------------------------------------------------------------------- #
# Glue Workflow + EventBridge (EventBridge só aceita workflow, não job direto) #
# --------------------------------------------------------------------------- #

resource "aws_glue_workflow" "etl" {
  name = "classicmodels-etl-workflow"
}

resource "aws_glue_trigger" "workflow_start" {
  name          = "classicmodels-etl-event-trigger"
  type          = "EVENT"
  workflow_name = aws_glue_workflow.etl.name

  actions {
    job_name = aws_glue_job.incremental_etl.name
  }

  depends_on = [aws_glue_job.incremental_etl]
}

resource "aws_cloudwatch_event_rule" "weekly_etl" {
  name                = "classicmodels-weekly-etl"
  description         = "Dispara o Glue ETL incremental toda segunda-feira ao meio-dia UTC"
  schedule_expression = "cron(0 12 ? * MON *)"
}

resource "aws_cloudwatch_event_target" "glue_job_target" {
  rule      = aws_cloudwatch_event_rule.weekly_etl.name
  target_id = "classicmodels-glue-job"
  arn       = aws_glue_workflow.etl.arn
  role_arn  = data.aws_iam_role.lab_role.arn

  depends_on = [aws_glue_trigger.workflow_start]
}
