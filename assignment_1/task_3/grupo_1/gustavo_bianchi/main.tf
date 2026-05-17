provider "aws" {
  region = "us-east-1"
}

# Lê o nome do bucket gerado na task 2
data "local_file" "bucket_name" {
  filename = "${path.module}/../../../task_2/grupo_1/gustavo_bianchi/bucket_name.txt"
}

# Permissão educacional
data "aws_iam_role" "lab_role" { name = "LabRole" }

# Cria o glue data catalog
resource "aws_glue_catalog_database" "analytics_db" {
  name        = "classicmodels_analytics_db"
  description = "Database analitico para o Athena (Task 3)"
}

# Cria o glue crawler
resource "aws_glue_crawler" "datalake_crawler" {
  name          = "classicmodels-s3-crawler"
  database_name = aws_glue_catalog_database.analytics_db.name
  role          = data.aws_iam_role.lab_role.arn

  s3_target {
    path = "s3://${data.local_file.bucket_name.content}/"
  }
}