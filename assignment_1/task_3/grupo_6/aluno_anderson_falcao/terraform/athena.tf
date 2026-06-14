# -- Athena & Glue Catalog --------------------------------------------------------

# Database no Glue Data Catalog para o Athena
resource "aws_glue_catalog_database" "analytics" {
  name        = "${var.project_name}_analytics"
  description = "Database analitico do classicmodels contendo as tabelas do star schema em formato parquet"
}

# Crawler para ler os arquivos Parquet no S3 e cadastrar as tabelas
resource "aws_glue_crawler" "analytics" {
  database_name = aws_glue_catalog_database.analytics.name
  name          = "${var.project_name}-analytics-crawler"
  role          = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/LabRole"

  s3_target {
    path = "s3://${aws_s3_bucket.etl.bucket}/data/fact_orders/"
  }
  s3_target {
    path = "s3://${aws_s3_bucket.etl.bucket}/data/dim_customers/"
  }
  s3_target {
    path = "s3://${aws_s3_bucket.etl.bucket}/data/dim_products/"
  }
  s3_target {
    path = "s3://${aws_s3_bucket.etl.bucket}/data/dim_dates/"
  }
  s3_target {
    path = "s3://${aws_s3_bucket.etl.bucket}/data/dim_countries/"
  }

  configuration = jsonencode({
    Version = 1.0,
    Grouping = {
      TableGroupingPolicy = "CombineCompatibleSchemas"
    }
  })

  tags = { Project = var.project_name }
}

# Bucket S3 para salvar os resultados das queries do Athena
resource "aws_s3_bucket" "athena_results" {
  bucket        = "${var.project_name}-athena-results-${data.aws_caller_identity.current.account_id}"
  force_destroy = true
  tags          = { Project = var.project_name }
}

resource "aws_s3_bucket_public_access_block" "athena_results" {
  bucket                  = aws_s3_bucket.athena_results.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Workgroup do Athena dedicado para a Task 3
resource "aws_athena_workgroup" "analytics" {
  name          = "${var.project_name}-analytics-workgroup"
  force_destroy = true

  configuration {
    result_configuration {
      output_location = "s3://${aws_s3_bucket.athena_results.bucket}/output/"
    }
  }

  tags = { Project = var.project_name }
}
