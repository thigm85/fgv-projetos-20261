resource "random_id" "suffix" {
  byte_length = 4
}

data "aws_subnet" "selected" {
  id = var.subnet_id
}

data "aws_route_tables" "selected_vpc" {
  vpc_id = var.vpc_id
}

resource "aws_vpc_endpoint" "s3_gateway" {
  vpc_id            = var.vpc_id
  service_name      = "com.amazonaws.${var.aws_region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = data.aws_route_tables.selected_vpc.ids
}

resource "aws_vpc_endpoint" "glue_interface" {
  vpc_id              = var.vpc_id
  service_name        = "com.amazonaws.${var.aws_region}.glue"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = [var.subnet_id]
  security_group_ids  = [aws_security_group.glue_job_sg.id]
  private_dns_enabled = true
}

resource "aws_s3_bucket" "etl_bucket" {
  bucket = "${var.project_name}-${random_id.suffix.hex}"
}

resource "aws_s3_bucket_versioning" "etl_bucket_versioning" {
  bucket = aws_s3_bucket.etl_bucket.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "etl_bucket_sse" {
  bucket = aws_s3_bucket.etl_bucket.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_policy" "etl_bucket_glue_role" {
  bucket = aws_s3_bucket.etl_bucket.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "AllowLabRoleGlueAccess"
        Effect    = "Allow"
        Principal = { AWS = var.glue_role_arn }
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:ListBucket"
        ]
        Resource = [
          aws_s3_bucket.etl_bucket.arn,
          "${aws_s3_bucket.etl_bucket.arn}/*"
        ]
      }
    ]
  })
}

resource "aws_security_group" "glue_job_sg" {
  name        = "${var.project_name}-glue-sg"
  description = "Security group for Glue JDBC connection"
  vpc_id      = var.vpc_id
}

resource "aws_security_group_rule" "glue_egress_all" {
  type              = "egress"
  from_port         = 0
  to_port           = 0
  protocol          = "-1"
  cidr_blocks       = ["0.0.0.0/0"]
  security_group_id = aws_security_group.glue_job_sg.id
}

resource "aws_security_group_rule" "glue_egress_self" {
  type                     = "egress"
  from_port                = 0
  to_port                  = 65535
  protocol                 = "tcp"
  security_group_id        = aws_security_group.glue_job_sg.id
  source_security_group_id = aws_security_group.glue_job_sg.id
}

resource "aws_security_group_rule" "glue_ingress_self" {
  type                     = "ingress"
  from_port                = 0
  to_port                  = 65535
  protocol                 = "tcp"
  security_group_id        = aws_security_group.glue_job_sg.id
  source_security_group_id = aws_security_group.glue_job_sg.id
}

resource "aws_security_group_rule" "allow_glue_to_rds" {
  type                     = "ingress"
  from_port                = var.db_port
  to_port                  = var.db_port
  protocol                 = "tcp"
  security_group_id        = var.db_security_group_id
  source_security_group_id = aws_security_group.glue_job_sg.id
}

resource "aws_s3_object" "glue_script" {
  bucket       = aws_s3_bucket.etl_bucket.id
  key          = "scripts/incremental_etl.py"
  source       = "${path.module}/../glue/incremental_etl.py"
  etag         = filemd5("${path.module}/../glue/incremental_etl.py")
  content_type = "text/x-python"
}

resource "aws_glue_connection" "mysql_connection" {
  name = "${var.project_name}-mysql-connection"

  connection_properties = {
    JDBC_CONNECTION_URL = "jdbc:mysql://${var.db_host}:${var.db_port}/${var.db_name}"
    USERNAME            = var.db_user
    PASSWORD            = var.db_password
  }

  physical_connection_requirements {
    availability_zone      = data.aws_subnet.selected.availability_zone
    security_group_id_list = [aws_security_group.glue_job_sg.id]
    subnet_id              = var.subnet_id
  }
}

resource "aws_glue_catalog_database" "analytics" {
  name = replace("${var.project_name}_analytics", "-", "_")
}

resource "aws_glue_catalog_table" "fact_orders" {
  name          = "fact_orders"
  database_name = aws_glue_catalog_database.analytics.name
  table_type    = "EXTERNAL_TABLE"

  parameters = {
    EXTERNAL           = "TRUE"
    "parquet.compress" = "SNAPPY"
  }

  storage_descriptor {
    location      = "s3://${aws_s3_bucket.etl_bucket.id}/analytics/fact_orders/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"

    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
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

resource "aws_glue_job" "etl_job" {
  name     = "${var.project_name}-incremental-etl"
  role_arn = var.glue_role_arn

  command {
    script_location = "s3://${aws_s3_bucket.etl_bucket.id}/${aws_s3_object.glue_script.key}"
    python_version  = "3"
  }

  glue_version      = "4.0"
  worker_type       = "G.1X"
  number_of_workers = 2
  timeout           = 60
  max_retries       = 0
  connections       = [aws_glue_connection.mysql_connection.name]

  default_arguments = {
    "--job-language"                     = "python"
    "--TempDir"                          = "s3://${aws_s3_bucket.etl_bucket.id}/temp/"
    "--enable-glue-datacatalog"          = "true"
    "--enable-continuous-cloudwatch-log" = "true"
    "--S3_BUCKET"                        = aws_s3_bucket.etl_bucket.id
    "--GLUE_DATABASE"                    = aws_glue_catalog_database.analytics.name
    "--DB_HOST"                          = var.db_host
    "--DB_USER"                          = var.db_user
    "--DB_PASSWORD"                      = var.db_password
    "--DB_NAME"                          = var.db_name
  }
}

resource "aws_glue_workflow" "etl" {
  name = "${var.project_name}-etl-workflow"
}

resource "aws_glue_trigger" "workflow_start" {
  name          = "${var.project_name}-event-trigger"
  type          = "EVENT"
  workflow_name = aws_glue_workflow.etl.name

  actions {
    job_name = aws_glue_job.etl_job.name
  }

  depends_on = [aws_glue_job.etl_job]
}

resource "aws_cloudwatch_event_rule" "glue_schedule" {
  name                = "${var.project_name}-glue-schedule"
  description         = "Dispara o Glue ETL incremental semanalmente (UTC)"
  schedule_expression = var.eventbridge_schedule
}

resource "aws_cloudwatch_event_target" "glue_job_target" {
  rule      = aws_cloudwatch_event_rule.glue_schedule.name
  target_id = "StartIncrementalGlueWorkflow"
  arn       = aws_glue_workflow.etl.arn
  role_arn  = var.glue_role_arn

  depends_on = [aws_glue_trigger.workflow_start]
}
