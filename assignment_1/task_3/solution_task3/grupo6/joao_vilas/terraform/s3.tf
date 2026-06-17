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

resource "aws_s3_bucket_versioning" "etl_bucket" {
  bucket = aws_s3_bucket.etl_bucket.id

  versioning_configuration {
    status = "Suspended"
  }
}

resource "aws_s3_bucket" "athena_results" {
  bucket        = local.athena_bucket_name
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

resource "aws_vpc_endpoint" "s3" {
  vpc_id            = data.aws_vpc.default.id
  service_name      = "com.amazonaws.${var.aws_region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = data.aws_route_tables.default.ids

  tags = {
    Name = "${var.project_prefix}-s3-endpoint"
  }
}

resource "aws_s3_object" "glue_script" {
  bucket = aws_s3_bucket.etl_bucket.id
  key    = local.glue_script_key
  source = "${path.module}/../glue/etl_classicmodels_star_schema.py"
  etag   = filemd5("${path.module}/../glue/etl_classicmodels_star_schema.py")
}

resource "aws_s3_object" "notebook" {
  bucket = aws_s3_bucket.etl_bucket.id
  key    = local.notebook_bucket_key
  source = "${path.module}/../notebooks/classicmodels_dashboard.ipynb"
  etag   = filemd5("${path.module}/../notebooks/classicmodels_dashboard.ipynb")
}
