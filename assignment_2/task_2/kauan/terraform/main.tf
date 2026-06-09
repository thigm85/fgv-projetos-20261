provider "aws" {
  region = var.aws_region
}

# 1. Bucket S3 para Scripts e Dados (Gold Layer)
# bucket_prefix garante um nome globalmente único, mas o Terraform o mantém no estado.
resource "aws_s3_bucket" "etl_bucket" {
  bucket_prefix = "fgv-etl-classicmodels-v3-"
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
  name_prefix = "glue-etl-sg-v3-"
  description = "Allow Glue to communicate with RDS and S3"
  vpc_id      = var.vpc_id

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

# Permissão no SG do RDS
resource "aws_security_group_rule" "allow_glue_to_rds" {
  type                     = "ingress"
  from_port                = 3306
  to_port                  = 3306
  protocol                 = "tcp"
  security_group_id        = var.rds_sg_id
  source_security_group_id = aws_security_group.glue_sg.id
}

# 3. IAM Role
data "aws_iam_role" "glue_role" {
  name = "LabRole"
}

# 4. Dados de Rede
data "aws_subnet" "selected" {
  id = var.subnet_id
}

# 5. Glue Connection
resource "aws_glue_connection" "mysql_conn" {
  name = "classicmodels-mysql-conn-v3"

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

# 5.1 VPC Endpoint para S3
resource "aws_vpc_endpoint" "s3" {
  vpc_id          = var.vpc_id
  service_name    = "com.amazonaws.${var.aws_region}.s3"
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
  name              = "classicmodels-etl-job-v3"
  role_arn          = data.aws_iam_role.glue_role.arn
  glue_version      = "4.0"
  worker_type       = "G.1X"
  number_of_workers = 2

  command {
    script_location = "s3://${aws_s3_bucket.etl_bucket.id}/${aws_s3_object.glue_script.key}"
    python_version  = "3"
  }

  connections = [aws_glue_connection.mysql_conn.name]

  default_arguments = {
    "--connection_name"      = aws_glue_connection.mysql_conn.name
    "--s3_output_path"       = "s3://${aws_s3_bucket.etl_bucket.id}/analytics/"
    "--db_name"              = var.db_name
    "--db_host"              = var.db_host
    "--db_port"              = var.db_port
    "--db_user"              = var.db_user
    "--db_password"          = var.db_password
    "--job-language"         = "python"
    "--continuous-log-logGroup"          = "/aws-glue/jobs/logs-v2/"
    "--enable-continuous-cloudwatch-log" = "true"
  }
}

# 7. Glue Catalog e Crawler
resource "aws_glue_catalog_database" "classicmodels_gold" {
  name = "classicmodels_gold_v3"
}

resource "aws_glue_crawler" "gold_crawler" {
  database_name = aws_glue_catalog_database.classicmodels_gold.name
  name          = "classicmodels-gold-crawler-v3"
  role          = data.aws_iam_role.glue_role.arn

  s3_target {
    path = "s3://${aws_s3_bucket.etl_bucket.id}/analytics/"
  }

  depends_on = [aws_s3_bucket.etl_bucket]
}

# 8. Athena Configuration
resource "aws_s3_bucket" "athena_results" {
  bucket_prefix = "athena-results-v3-"
  force_destroy = true
}

resource "aws_athena_workgroup" "main" {
  name = "classicmodels_workgroup_v3"

  configuration {
    enforce_workgroup_configuration    = true
    publish_cloudwatch_metrics_enabled = true

    result_configuration {
      output_location = "s3://${aws_s3_bucket.athena_results.id}/results/"
    }
  }

  force_destroy = true
}

# 9. EventBridge Scheduling (Task 2)
# Nota: O EventBridge (CloudWatch Events) legado não aceita ARNs de Glue Job como alvos diretos em sua API (PutTargets retorna "Provided Arn is not in correct format").
# Como fallback e melhor prática nativa, mantemos a regra documentada e comentada, e usamos o aws_glue_trigger do próprio Glue para agendamento.

# resource "aws_cloudwatch_event_rule" "glue_schedule" {
#   name                = "classicmodels-glue-schedule"
#   description         = "Trigger Glue job weekly on Monday noon"
#   schedule_expression = "cron(0 12 ? * MON *)"
# }

# resource "aws_cloudwatch_event_target" "glue_target" {
#   rule      = aws_cloudwatch_event_rule.glue_schedule.name
#   target_id = "TriggerGlueJob"
#   arn       = aws_glue_job.etl_job.arn
#   role_arn  = data.aws_iam_role.glue_role.arn
# }

resource "aws_glue_trigger" "glue_schedule_trigger" {
  name     = "classicmodels-glue-schedule-trigger-v3"
  type     = "SCHEDULED"
  schedule = "cron(0 12 ? * MON *)"
  enabled  = true

  actions {
    job_name = aws_glue_job.etl_job.name
  }
}
