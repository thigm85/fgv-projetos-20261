terraform {
    required_providers {
        aws = {
            source = "hashicorp/aws"
            version = "~> 5.0"
        }
    }
}

# Lendo as configurações
locals {
    credentials = jsondecode(file("${path.module}/config/db_credentials.json"))
    endpoint = jsondecode(file("${path.module}/config/db_endpoint.json"))
    etl_cfg = jsondecode(file("${path.module}/config/etl_configs.json"))

    # Extraindo a variável do bucket
    bucket_name = local.etl_cfg.bucket_name
}

provider "aws" {
    region = local.etl_cfg.region
}

# Capturando a rede padrão do Lab
data "aws_vpc" "default" {
    default = true
}

data "aws_subnets" "default" {
    filter {
        name = "vpc-id"
        values = [data.aws_vpc.default.id]
    }
}

data "aws_subnet" "selected" {
    id = data.aws_subnets.default.ids[0]
}

# Capturando as tabelas de roteamento da VPC
data "aws_route_tables" "default" {
    vpc_id = data.aws_vpc.default.id
}

# Criando o bucket S3 e fazendo o upload do script
resource "aws_s3_bucket" "datalake" {
    bucket = local.bucket_name
    force_destroy = true
}

# Fazendo o upload automático do script de ETL para o S3
resource "aws_s3_object" "etl_script" {
    bucket = aws_s3_bucket.datalake.id
    key = "scripts/etl_job.py"
    source = "${path.module}/etl_job.py"
    etag = filemd5("${path.module}/etl_job.py")
}

# VPC endpoint para o S3
resource "aws_vpc_endpoint" "s3" {
    vpc_id = data.aws_vpc.default.id
    service_name = "com.amazonaws.us-east-1.s3"
    route_table_ids = data.aws_route_tables.default.ids
}

# Security group do Glue
resource "aws_security_group" "glue_sg" {
    name = "glue_vpc_connection_sg"
    description = "Security Group para o AWS Glue"
    vpc_id = data.aws_vpc.default.id

    ingress {
        from_port = 0
        to_port = 65535
        protocol = "tcp"
        self = true
    }

    # Regra exigida pelos nós do Glue para se comunicarem
    egress {
        from_port = 0
        to_port = 0
        protocol = "-1"
        self = true
    }

    # Saída para acessar o S3 e o RDS
    egress {
        from_port = 0
        to_port = 0
        protocol = "-1"
        cidr_blocks = ["0.0.0.0/0"]
    }
}

# Capturando a Role padrão do AWS Academy
data "aws_iam_role" "lab_role" {
    name = "LabRole"
}

# Conexão do Glue com o RDS
resource "aws_glue_connection" "rds_conn" {
    name = "rds_mysql_connection"

    connection_properties = {
        JDBC_CONNECTION_URL = "jdbc:mysql://${local.endpoint.host}:${local.endpoint.port}/classicmodels"
        USERNAME = local.credentials.db_user
        PASSWORD = local.credentials.db_password
    }

    physical_connection_requirements {
        security_group_id_list = [aws_security_group.glue_sg.id]
        subnet_id = data.aws_subnets.default.ids[0]
        availability_zone = data.aws_subnet.selected.availability_zone
    }
}

# Job do Glue
resource "aws_glue_job" "etl_job" {
    name = "classicmodels_star_schema_etl"
    role_arn = data.aws_iam_role.lab_role.arn

    command {
        script_location = "s3://${aws_s3_bucket.datalake.bucket}/${aws_s3_object.etl_script.key}"
        python_version = "3"
    }

    default_arguments = {
        "--JOB_NAME" = "classicmodels_star_schema_etl"
        "--S3_TARGET_PATH" = "s3://${aws_s3_bucket.datalake.bucket}/output"
        "--TempDir" = "s3://${aws_s3_bucket.datalake.bucket}/temp"
        "--job-language" = "python"
        "--DB_HOST"        = local.endpoint.host
        "--DB_USER"        = local.credentials.db_user
        "--DB_PASS"        = local.credentials.db_password
        "--DB_NAME"        = "classicmodels"
    }

    connections = [aws_glue_connection.rds_conn.name]

    # Configurações de performance/custo
    glue_version = "4.0"
    worker_type = "G.1X"
    number_of_workers = 2
    max_retries = 0
}

# Cria um Workflow
resource "aws_glue_workflow" "etl_workflow" {
  name = "classicmodels_etl_workflow"
}

# Regra do EventBridge
resource "aws_cloudwatch_event_rule" "weekly_etl_trigger" {
  name                = "trigger_classicmodels_etl_weekly"
  description         = "Dispara o workflow de ETL do classicmodels semanalmente"
  schedule_expression = "cron(0 12 ? * MON *)" 
}

# Alvo do EventBridge
resource "aws_cloudwatch_event_target" "glue_workflow_target" {
  rule      = aws_cloudwatch_event_rule.weekly_etl_trigger.name
  target_id = "TriggerGlueWorkflow"
  arn       = aws_glue_workflow.etl_workflow.arn
  role_arn  = data.aws_iam_role.lab_role.arn 
}

# Trigger interno do Glue para rodar o Job quando o Workflow iniciar
resource "aws_glue_trigger" "workflow_job_trigger" {
  name          = "start_classicmodels_job"
  type          = "ON_DEMAND"
  workflow_name = aws_glue_workflow.etl_workflow.name

  actions {
    job_name = aws_glue_job.etl_job.name
  }
}

# Banco de dados no Glue Catalog para o Athena
resource "aws_glue_catalog_database" "analytics_db" {
  name = "classicmodels_analytics"
}

# Tabela externa no Glue Catalog declarando as partições order_year e order_month
resource "aws_glue_catalog_table" "fact_orders_table" {
  name          = "fact_orders"
  database_name = aws_glue_catalog_database.analytics_db.name
  table_type    = "EXTERNAL_TABLE"

  parameters = {
    EXTERNAL              = "TRUE"
    "parquet.compression" = "SNAPPY"
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
    location      = "s3://${aws_s3_bucket.datalake.bucket}/output/fact_orders/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"

    ser_de_info {
      name                  = "my-stream"
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
      parameters = {
        "serialization.format" = 1
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