resource "aws_s3_bucket" "etl_bucket" {
  bucket        = local.etl_bucket_name
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "etl_bucket" {
  bucket = aws_s3_bucket.etl_bucket.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "etl_bucket" {
  bucket = aws_s3_bucket.etl_bucket.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Bucket separado para resultados do Athena (validação --athena).
resource "aws_s3_bucket" "athena_results" {
  bucket        = "${var.project_prefix}-athena-${local.account_id}-${var.aws_region}"
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "athena_results" {
  bucket = aws_s3_bucket.athena_results.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "athena_results" {
  bucket = aws_s3_bucket.athena_results.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "athena_results" {
  bucket = aws_s3_bucket.athena_results.id

  rule {
    id     = "expire-query-results"
    status = "Enabled"

    filter {
      prefix = "results/"
    }

    expiration {
      days = 7
    }
  }
}

# Gateway endpoint p/ S3: tráfego Glue->S3 sem sair para a internet.
resource "aws_vpc_endpoint" "s3" {
  vpc_id            = data.aws_vpc.default.id
  service_name      = "com.amazonaws.${var.aws_region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = data.aws_route_tables.default.ids

  tags = {
    Name = "${var.project_prefix}-s3-endpoint"
  }
}

# Interface endpoint para Secrets Manager: o Glue Job roda na VPC (via Glue Connection)
# sem IP público, então precisa deste endpoint para ler o secret com as credenciais do RDS.
# O self-rule do glue_sg já libera 443 entre as ENIs do Glue e o endpoint.
resource "aws_vpc_endpoint" "secretsmanager" {
  vpc_id              = data.aws_vpc.default.id
  service_name        = "com.amazonaws.${var.aws_region}.secretsmanager"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = [data.aws_subnet.glue_subnet.id]
  security_group_ids  = [aws_security_group.glue_sg.id]
  private_dns_enabled = true

  tags = {
    Name = "${var.project_prefix}-secretsmanager-endpoint"
  }
}

# Caminho relativo ao módulo (3.1.1): o script existe no repositório entregue.
resource "aws_s3_object" "glue_script" {
  bucket = aws_s3_bucket.etl_bucket.id
  key    = local.glue_script_key
  source = "${path.module}/../glue/etl_classicmodels_incremental.py"
  etag   = filemd5("${path.module}/../glue/etl_classicmodels_incremental.py")
}
