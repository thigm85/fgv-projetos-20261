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

data "aws_caller_identity" "current" {}

locals {
  bucket_name          = var.etl_bucket_name != "" ? var.etl_bucket_name : "classicmodels-etl-${data.aws_caller_identity.current.account_id}-${var.region}"
  glue_script_key      = "scripts/glue_incremental_etl.py"
  glue_role_arn        = var.existing_glue_role_arn != "" ? var.existing_glue_role_arn : aws_iam_role.glue_role[0].arn
  glue_role_name       = var.existing_glue_role_name != "" ? var.existing_glue_role_name : try(aws_iam_role.glue_role[0].name, "")
  eventbridge_role_arn = var.existing_eventbridge_role_arn != "" ? var.existing_eventbridge_role_arn : aws_iam_role.eventbridge_glue[0].arn
  analytics_root       = "s3://${aws_s3_bucket.etl.id}/analytics"
  use_vpc_connection   = var.glue_subnet_id != "" && var.glue_security_group_id != "" && var.glue_availability_zone != ""
  create_s3_endpoint   = var.glue_vpc_id != "" && length(var.glue_route_table_ids) > 0
}

# ── S3 ────────────────────────────────────────────────────────────────────────

resource "aws_s3_bucket" "etl" {
  bucket = local.bucket_name
  tags   = { Name = local.bucket_name }
}

resource "aws_s3_bucket_versioning" "etl" {
  bucket = aws_s3_bucket.etl.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "etl" {
  bucket = aws_s3_bucket.etl.id
  rule {
    apply_server_side_encryption_by_default { sse_algorithm = "AES256" }
  }
}

# ── VPC endpoint (optional, required when Glue runs inside a VPC) ─────────────

resource "aws_vpc_endpoint" "s3_gateway" {
  count             = local.create_s3_endpoint ? 1 : 0
  vpc_id            = var.glue_vpc_id
  service_name      = "com.amazonaws.${var.region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = var.glue_route_table_ids
  tags              = { Name = "classicmodels-glue-s3-endpoint" }
}

# ── Upload Glue script ────────────────────────────────────────────────────────

resource "aws_s3_object" "glue_script" {
  bucket = aws_s3_bucket.etl.id
  key    = local.glue_script_key
  source = "${path.module}/../scripts/glue_incremental_etl.py"
  etag   = filemd5("${path.module}/../scripts/glue_incremental_etl.py")
}

# ── IAM — Glue role (created only when no existing role is provided) ──────────

resource "aws_iam_role" "glue_role" {
  count = var.existing_glue_role_arn == "" ? 1 : 0
  name  = "classicmodels-incremental-glue-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "glue.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "glue_service" {
  count      = var.existing_glue_role_arn == "" ? 1 : 0
  role       = aws_iam_role.glue_role[0].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole"
}

resource "aws_iam_role_policy" "glue_inline" {
  count = var.existing_glue_role_arn == "" ? 1 : 0
  name  = "classicmodels-glue-inline"
  role  = aws_iam_role.glue_role[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = ["s3:PutObject", "s3:GetObject", "s3:DeleteObject", "s3:ListBucket",
                  "s3:ListBucketVersions", "s3:DeleteObjectVersion"]
        Resource = [aws_s3_bucket.etl.arn, "${aws_s3_bucket.etl.arn}/*"]
      },
      {
        Effect   = "Allow"
        Action   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "arn:aws:logs:${var.region}:${data.aws_caller_identity.current.account_id}:log-group:/aws-glue/*"
      },
      {
        Effect = "Allow"
        Action = ["ec2:CreateNetworkInterface", "ec2:DeleteNetworkInterface",
                  "ec2:DescribeNetworkInterfaces", "ec2:DescribeSubnets",
                  "ec2:DescribeSecurityGroups", "ec2:DescribeRouteTables",
                  "ec2:DescribeVpcEndpoints", "ec2:DescribeVpcAttribute", "ec2:DescribeVpcs"]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = ["glue:GetDatabase", "glue:GetTable", "glue:GetPartitions",
                  "glue:CreatePartition", "glue:BatchCreatePartition", "glue:UpdatePartition"]
        Resource = "*"
      }
    ]
  })
}

# ── Glue connection (JDBC to RDS) ─────────────────────────────────────────────

resource "aws_glue_connection" "rds_mysql" {
  name = var.glue_connection_name

  connection_properties = {
    JDBC_CONNECTION_URL = "jdbc:mysql://${var.rds_host}:${var.rds_port}/${var.db_name}"
    USERNAME            = var.db_username
    PASSWORD            = var.db_password
  }

  dynamic "physical_connection_requirements" {
    for_each = local.use_vpc_connection ? [1] : []
    content {
      availability_zone      = var.glue_availability_zone
      security_group_id_list = [var.glue_security_group_id]
      subnet_id              = var.glue_subnet_id
    }
  }
}

# ── Glue Data Catalog ─────────────────────────────────────────────────────────

resource "aws_glue_catalog_database" "analytics" {
  name = var.glue_database_name
}

resource "aws_glue_catalog_table" "dim_customers" {
  name          = "dim_customers"
  database_name = aws_glue_catalog_database.analytics.name
  table_type    = "EXTERNAL_TABLE"
  parameters    = { classification = "parquet", EXTERNAL = "TRUE" }

  storage_descriptor {
    location      = "${local.analytics_root}/dim_customers/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"
    ser_de_info { serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe" }
    columns { name = "customer_id";   type = "int"    }
    columns { name = "customer_name"; type = "string" }
    columns { name = "contact_name";  type = "string" }
    columns { name = "city";          type = "string" }
    columns { name = "country";       type = "string" }
  }
}

resource "aws_glue_catalog_table" "dim_products" {
  name          = "dim_products"
  database_name = aws_glue_catalog_database.analytics.name
  table_type    = "EXTERNAL_TABLE"
  parameters    = { classification = "parquet", EXTERNAL = "TRUE" }

  storage_descriptor {
    location      = "${local.analytics_root}/dim_products/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"
    ser_de_info { serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe" }
    columns { name = "product_id";     type = "string" }
    columns { name = "product_name";   type = "string" }
    columns { name = "product_line";   type = "string" }
    columns { name = "product_vendor"; type = "string" }
  }
}

resource "aws_glue_catalog_table" "dim_dates" {
  name          = "dim_dates"
  database_name = aws_glue_catalog_database.analytics.name
  table_type    = "EXTERNAL_TABLE"
  parameters    = { classification = "parquet", EXTERNAL = "TRUE" }

  storage_descriptor {
    location      = "${local.analytics_root}/dim_dates/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"
    ser_de_info { serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe" }
    columns { name = "date_key";  type = "int"  }
    columns { name = "full_date"; type = "date" }
    columns { name = "year";      type = "int"  }
    columns { name = "quarter";   type = "int"  }
    columns { name = "month";     type = "int"  }
    columns { name = "day";       type = "int"  }
  }
}

resource "aws_glue_catalog_table" "dim_countries" {
  name          = "dim_countries"
  database_name = aws_glue_catalog_database.analytics.name
  table_type    = "EXTERNAL_TABLE"
  parameters    = { classification = "parquet", EXTERNAL = "TRUE" }

  storage_descriptor {
    location      = "${local.analytics_root}/dim_countries/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"
    ser_de_info { serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe" }
    columns { name = "country_key"; type = "int"    }
    columns { name = "country";     type = "string" }
    columns { name = "territory";   type = "string" }
  }
}

resource "aws_glue_catalog_table" "fact_orders" {
  name          = "fact_orders"
  database_name = aws_glue_catalog_database.analytics.name
  table_type    = "EXTERNAL_TABLE"

  # Partition projection lets Athena query partitions without MSCK REPAIR TABLE
  parameters = {
    classification                 = "parquet"
    EXTERNAL                       = "TRUE"
    "projection.enabled"           = "true"
    "projection.order_year.type"   = "integer"
    "projection.order_year.range"  = "2003,2100"
    "projection.order_month.type"  = "integer"
    "projection.order_month.range" = "1,12"
    "storage.location.template"    = "${local.analytics_root}/fact_orders/order_year=$${order_year}/order_month=$${order_month}/"
  }

  partition_keys { name = "order_year";  type = "int" }
  partition_keys { name = "order_month"; type = "int" }

  storage_descriptor {
    location      = "${local.analytics_root}/fact_orders/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"
    ser_de_info { serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe" }
    columns { name = "order_id";        type = "int"    }
    columns { name = "customer_id";     type = "int"    }
    columns { name = "product_id";      type = "string" }
    columns { name = "order_date_key";  type = "int"    }
    columns { name = "country_key";     type = "int"    }
    columns { name = "quantity_ordered"; type = "int"   }
    columns { name = "price_each";      type = "double" }
    columns { name = "sales_amount";    type = "double" }
  }
}

# ── Glue Job ──────────────────────────────────────────────────────────────────

resource "aws_glue_job" "classicmodels_incremental_etl" {
  name              = var.glue_job_name
  role_arn          = local.glue_role_arn
  glue_version      = "4.0"
  worker_type       = "G.1X"
  number_of_workers = var.glue_workers
  timeout           = 20
  max_retries       = 0

  command {
    script_location = "s3://${aws_s3_bucket.etl.id}/${local.glue_script_key}"
    python_version  = "3"
  }

  connections = [aws_glue_connection.rds_mysql.name]

  default_arguments = {
    "--job-language"                     = "python"
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-metrics"                   = "true"
    "--extra-py-files"                   = ""
    "--TempDir"                          = "s3://${aws_s3_bucket.etl.id}/tmp"
    "--JOB_NAME"                         = var.glue_job_name
    "--S3_BUCKET"                        = aws_s3_bucket.etl.id
    "--GLUE_DATABASE"                    = aws_glue_catalog_database.analytics.name
    "--DB_HOST"                          = var.rds_host
    "--DB_USER"                          = var.db_username
    "--DB_PASSWORD"                      = var.db_password
    "--DB_NAME"                          = var.db_name
  }

  depends_on = [
    aws_s3_object.glue_script,
    aws_glue_connection.rds_mysql,
    aws_glue_catalog_table.fact_orders,
    aws_vpc_endpoint.s3_gateway,
  ]
}

# ── EventBridge Scheduler (weekly trigger) ────────────────────────────────────

resource "aws_iam_role" "eventbridge_glue" {
  count = var.existing_eventbridge_role_arn == "" ? 1 : 0
  name  = "classicmodels-eventbridge-glue-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "scheduler.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "eventbridge_start_glue" {
  count = var.existing_eventbridge_role_arn == "" ? 1 : 0
  name  = "classicmodels-eventbridge-start-glue"
  role  = aws_iam_role.eventbridge_glue[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "glue:StartJobRun"
      Resource = aws_glue_job.classicmodels_incremental_etl.arn
    }]
  })
}

resource "aws_scheduler_schedule" "weekly_etl" {
  name        = "classicmodels-incremental-etl-weekly"
  description = "Triggers the classicmodels incremental Glue ETL weekly."

  flexible_time_window { mode = "OFF" }

  schedule_expression = var.eventbridge_schedule_expression

  target {
    arn      = "arn:aws:scheduler:::aws-sdk:glue:startJobRun"
    role_arn = local.eventbridge_role_arn
    input    = jsonencode({ JobName = aws_glue_job.classicmodels_incremental_etl.name })
  }
}
