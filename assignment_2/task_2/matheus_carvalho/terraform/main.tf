locals {
  bucket_name = var.bucket_name != "" ? var.bucket_name : "${var.project_prefix}-${data.aws_caller_identity.current.account_id}"
}

data "aws_caller_identity" "current" {}

# 1. Recupera a Role IAM existente (LabRole no AWS Academy)
data "aws_iam_role" "existing_glue" {
  name = var.existing_glue_role_name
}

# 2. Recupera a instância RDS classicmodels-db que já está ativa
data "aws_db_instance" "classicmodels" {
  db_instance_identifier = var.db_identifier
}

# 3. Recupera VPC e Subnets padrão do ambiente
data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

data "aws_subnet" "selected" {
  vpc_id            = data.aws_vpc.default.id
  availability_zone = data.aws_db_instance.classicmodels.availability_zone
}

data "aws_route_tables" "default" {
  vpc_id = data.aws_vpc.default.id
}

# 4. Cria o VPC Endpoint para o S3 (necessário para o Glue acessar o S3 na VPC)
resource "aws_vpc_endpoint" "s3" {
  vpc_id          = data.aws_vpc.default.id
  service_name    = "com.amazonaws.${var.aws_region}.s3"
  route_table_ids = data.aws_route_tables.default.ids

  tags = {
    Name = "${var.project_prefix}-s3-endpoint"
  }
}

# 5. Security Group para o Glue
resource "aws_security_group" "glue" {
  name        = "${var.project_prefix}-glue-sg"
  description = "Acesso de rede para o Job Glue"
  vpc_id      = data.aws_vpc.default.id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.project_prefix}-glue-sg"
  }
}

resource "aws_security_group_rule" "glue_self_ingress" {
  type                     = "ingress"
  from_port                = 0
  to_port                  = 65535
  protocol                 = "tcp"
  security_group_id        = aws_security_group.glue.id
  source_security_group_id = aws_security_group.glue.id
  description              = "Comunicacao interna do Glue"
}

# 6. Libera o RDS para receber conexões vindas do Security Group do Glue
resource "aws_security_group_rule" "rds_from_glue" {
  type                     = "ingress"
  from_port                = data.aws_db_instance.classicmodels.port
  to_port                  = data.aws_db_instance.classicmodels.port
  protocol                 = "tcp"
  security_group_id        = data.aws_db_instance.classicmodels.vpc_security_groups[0]
  source_security_group_id = aws_security_group.glue.id
  description              = "Acesso JDBC vindo do Glue"
}

# 7. S3 Bucket do Data Lake
resource "aws_s3_bucket" "analytics" {
  bucket        = local.bucket_name
  force_destroy = true

  tags = {
    Name = "${var.project_prefix}-analytics"
  }
}

resource "aws_s3_bucket_versioning" "analytics" {
  bucket = aws_s3_bucket.analytics.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "analytics" {
  bucket = aws_s3_bucket.analytics.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# 8. Upload do Script do Glue Job para o S3
resource "aws_s3_object" "glue_script" {
  bucket       = aws_s3_bucket.analytics.id
  key          = var.glue_script_key
  source       = "${path.module}/../glue/etl_job.py"
  etag         = filemd5("${path.module}/../glue/etl_job.py")
  content_type = "text/x-python"
}

# 9. Glue Connection para o RDS
resource "aws_glue_connection" "classicmodels_incremental" {
  name = var.glue_connection_name

  connection_type = "JDBC"

  connection_properties = {
    JDBC_CONNECTION_URL = "jdbc:mysql://${data.aws_db_instance.classicmodels.address}:${data.aws_db_instance.classicmodels.port}/${var.db_name}"
    USERNAME            = data.aws_db_instance.classicmodels.master_username
    # Senha deve ser fornecida via variável sensitiva ou preenchida no tfvars
    PASSWORD            = data.aws_db_instance.classicmodels.master_username == "admin" ? "FGV_Projetos_2026!" : "ClassicModels123!" 
  }

  physical_connection_requirements {
    availability_zone      = data.aws_db_instance.classicmodels.availability_zone
    security_group_id_list = [aws_security_group.glue.id]
    subnet_id              = data.aws_subnet.selected.id
  }

  depends_on = [aws_vpc_endpoint.s3]
}

# 10. Glue Job Incremental
resource "aws_glue_job" "classicmodels_incremental" {
  name     = var.glue_job_name
  role_arn = data.aws_iam_role.existing_glue.arn

  glue_version      = "4.0"
  max_retries       = 0
  timeout           = 15
  number_of_workers = 2
  worker_type       = "G.1X"

  execution_property {
    max_concurrent_runs = 3
  }

  command {
    name            = "glueetl"
    script_location = "s3://${aws_s3_bucket.analytics.bucket}/${aws_s3_object.glue_script.key}"
    python_version  = "3"
  }

  connections = [aws_glue_connection.classicmodels_incremental.name]

  default_arguments = {
    "--job-language"                      = "python"
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-glue-datacatalog"          = "false"
    "--TempDir"                          = "s3://${aws_s3_bucket.analytics.bucket}/tmp/"
    "--db_host"                          = data.aws_db_instance.classicmodels.address
    "--db_port"                          = tostring(data.aws_db_instance.classicmodels.port)
    "--db_name"                          = var.db_name
    "--db_user"                          = data.aws_db_instance.classicmodels.master_username
    "--db_password"                      = data.aws_db_instance.classicmodels.master_username == "admin" ? "FGV_Projetos_2026!" : "ClassicModels123!"
    "--output_bucket"                    = aws_s3_bucket.analytics.bucket
    "--output_prefix"                    = "analytics"
  }

  depends_on = [
    aws_s3_object.glue_script,
    aws_glue_connection.classicmodels_incremental
  ]
}

# 11. Glue Workflow e Trigger (EventBridge -> Workflow -> Job)
resource "aws_glue_workflow" "classicmodels" {
  name = "${var.project_prefix}-workflow"
}

resource "aws_glue_trigger" "workflow_event_trigger" {
  name          = "${var.project_prefix}-event-trigger"
  type          = "EVENT"
  workflow_name = aws_glue_workflow.classicmodels.name

  actions {
    job_name = aws_glue_job.classicmodels_incremental.name
  }
}

# 12. Agendamento com EventBridge (Cron)
resource "aws_cloudwatch_event_rule" "glue_cron" {
  name                = "${var.project_prefix}-glue-cron-rule"
  description         = "Agenda a execucao do Glue Job incremental"
  schedule_expression = var.cron_expression
}

resource "aws_cloudwatch_event_target" "glue_trigger" {
  rule      = aws_cloudwatch_event_rule.glue_cron.name
  target_id = "TriggerIncrementalGlueWorkflow"
  arn       = aws_glue_workflow.classicmodels.arn
  role_arn  = data.aws_iam_role.existing_glue.arn
}

# 13. Permissão do EventBridge para iniciar o Glue Workflow
# Se o IAM bloquear modificações em roles compartilhadas, isso será apenas informativo.
resource "aws_iam_policy" "eventbridge_glue" {
  name        = "${var.project_prefix}-eventbridge-glue-policy"
  description = "Permissao para o EventBridge disparar o Glue Workflow"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = [
          "glue:NotifyEvent",
          "glue:StartWorkflowRun"
        ]
        Resource = aws_glue_workflow.classicmodels.arn
      }
    ]
  })
}

# 13. Catalogo Glue
resource "aws_glue_catalog_database" "analytics" {
  name = "classicmodels_analytics"
}

resource "aws_glue_catalog_table" "fact_orders" {
  name          = "fact_orders"
  database_name = aws_glue_catalog_database.analytics.name
  table_type    = "EXTERNAL_TABLE"

  parameters = {
    "classification" = "parquet"
  }

  partition_keys {
    name = "order_year"
    type = "int"
  }

  partition_keys {
    name = "order_month"
    type = "int"
  }

  storage_descriptor {
    location      = "s3://${aws_s3_bucket.analytics.bucket}/analytics/fact_orders/"
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
      type = "int"
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
}

resource "aws_glue_catalog_table" "dim_customers" {
  name          = "dim_customers"
  database_name = aws_glue_catalog_database.analytics.name
  table_type    = "EXTERNAL_TABLE"

  parameters = {
    "classification" = "parquet"
  }

  storage_descriptor {
    location      = "s3://${aws_s3_bucket.analytics.bucket}/analytics/dim_customers/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"

    ser_de_info {
      name                  = "parquet"
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
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

resource "aws_glue_catalog_table" "dim_products" {
  name          = "dim_products"
  database_name = aws_glue_catalog_database.analytics.name
  table_type    = "EXTERNAL_TABLE"

  parameters = {
    "classification" = "parquet"
  }

  storage_descriptor {
    location      = "s3://${aws_s3_bucket.analytics.bucket}/analytics/dim_products/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"

    ser_de_info {
      name                  = "parquet"
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
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

resource "aws_glue_catalog_table" "dim_dates" {
  name          = "dim_dates"
  database_name = aws_glue_catalog_database.analytics.name
  table_type    = "EXTERNAL_TABLE"

  parameters = {
    "classification" = "parquet"
  }

  storage_descriptor {
    location      = "s3://${aws_s3_bucket.analytics.bucket}/analytics/dim_dates/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"

    ser_de_info {
      name                  = "parquet"
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
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

resource "aws_glue_catalog_table" "dim_countries" {
  name          = "dim_countries"
  database_name = aws_glue_catalog_database.analytics.name
  table_type    = "EXTERNAL_TABLE"

  parameters = {
    "classification" = "parquet"
  }

  storage_descriptor {
    location      = "s3://${aws_s3_bucket.analytics.bucket}/analytics/dim_countries/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"

    ser_de_info {
      name                  = "parquet"
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
    }

    columns {
      name = "country_key"
      type = "string"
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
