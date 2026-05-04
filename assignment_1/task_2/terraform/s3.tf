##############################################################################
# S3 Buckets
#
# 1. etl_output  — armazena os Parquets resultantes (star schema)
# 2. glue_assets — armazena o script ETL + diretório temporário do Glue
##############################################################################

# ─── Bucket de saída (dados transformados em Parquet) ───────────────────────
resource "aws_s3_bucket" "etl_output" {
  bucket        = "${var.project_name}-output-${data.aws_caller_identity.current.account_id}"
  force_destroy = true # Lab — permite destruir o bucket com objetos dentro
  tags = {
    Project = var.project_name
    Purpose = "ETL output - star schema Parquet files"
  }
}

# ─── Bucket de assets do Glue (scripts + temp) ─────────────────────────────
resource "aws_s3_bucket" "glue_assets" {
  bucket        = "${var.project_name}-assets-${data.aws_caller_identity.current.account_id}"
  force_destroy = true
  tags = {
    Project = var.project_name
    Purpose = "Glue job scripts and temp directory"
  }
}

# ─── Upload do script ETL para o S3 ────────────────────────────────────────
resource "aws_s3_object" "etl_script" {
  bucket = aws_s3_bucket.glue_assets.id
  key    = "scripts/etl_classicmodels.py"
  source = "${path.module}/../scripts/etl_classicmodels.py"
  etag   = filemd5("${path.module}/../scripts/etl_classicmodels.py")
}
