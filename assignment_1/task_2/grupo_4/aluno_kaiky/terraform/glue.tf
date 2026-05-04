data "archive_file" "glue_modules" {
  type        = "zip"
  source_dir  = abspath("${path.module}/../glue_jobs")
  output_path = "${path.module}/build/glue_modules.zip"
  excludes    = ["etl_job.py"]
}

locals {
  use_existing_glue_role = trimspace(var.glue_job_role_arn) != ""
}

resource "aws_s3_object" "glue_entry_script" {
  bucket = aws_s3_bucket.data_lake.id
  key    = "${local.script_prefix}/etl_job.py"
  source = abspath("${path.module}/../glue_jobs/etl_job.py")
  etag   = filemd5(abspath("${path.module}/../glue_jobs/etl_job.py"))
}

resource "aws_s3_object" "glue_modules_zip" {
  bucket = aws_s3_bucket.data_lake.id
  key    = "${local.script_prefix}/glue_modules.zip"
  source = data.archive_file.glue_modules.output_path
  etag   = data.archive_file.glue_modules.output_md5
}

data "aws_iam_policy_document" "glue_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["glue.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "glue_etl" {
  count              = local.use_existing_glue_role ? 0 : 1
  name               = "${local.name}-glue-role"
  assume_role_policy = data.aws_iam_policy_document.glue_assume.json

  tags = {
    Project = local.name
  }
}

data "aws_iam_policy_document" "glue_job_minimal" {
  statement {
    sid = "CloudWatchLogs"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = ["arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws-glue/*"]
  }

  statement {
    sid = "GlueConnection"
    actions = [
      "glue:GetConnection",
      "glue:GetConnections",
    ]
    resources = ["*"]
  }

  statement {
    sid       = "S3ListBucket"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.data_lake.arn]
  }

  statement {
    sid = "S3ObjectWarehouse"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
    ]
    resources = ["${aws_s3_bucket.data_lake.arn}/${local.data_prefix}/*"]
  }

  statement {
    sid = "S3ObjectScripts"
    actions = [
      "s3:GetObject",
    ]
    resources = ["${aws_s3_bucket.data_lake.arn}/${local.script_prefix}/*"]
  }

  statement {
    sid = "GlueENIsForVPC"
    actions = [
      "ec2:CreateNetworkInterface",
      "ec2:DeleteNetworkInterface",
      "ec2:DescribeNetworkInterfaces",
      "ec2:DescribeSecurityGroups",
      "ec2:DescribeSubnets",
      "ec2:DescribeVpcEndpoints",
      "ec2:DescribeRouteTables",
      "ec2:DescribeVpcAttribute",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "glue_etl_inline" {
  count  = local.use_existing_glue_role ? 0 : 1
  name   = "${local.name}-glue-inline"
  role   = aws_iam_role.glue_etl[0].id
  policy = data.aws_iam_policy_document.glue_job_minimal.json
}

resource "aws_glue_job" "classicmodels_star_schema" {
  count             = length(aws_glue_connection.mysql) > 0 ? 1 : 0
  name              = "${local.name}-star-schema"
  role_arn          = local.use_existing_glue_role ? var.glue_job_role_arn : aws_iam_role.glue_etl[0].arn
  glue_version      = var.glue_version
  worker_type       = var.glue_worker_type
  number_of_workers = var.glue_number_of_workers
  max_retries       = 1
  timeout           = 60

  command {
    name            = "glueetl"
    python_version  = var.python_version
    script_location = "s3://${aws_s3_bucket.data_lake.bucket}/${local.script_prefix}/etl_job.py"
  }

  connections = [aws_glue_connection.mysql[count.index].name]

  default_arguments = {
    "--job-language"                     = "python"
    "--extra-py-files"                 = "s3://${aws_s3_bucket.data_lake.bucket}/${local.script_prefix}/glue_modules.zip"
    "--enable-metrics"                 = "true"
    "--enable-continuous-cloudwatch-log" = "true"
    "--GLUE_CONNECTION_NAME"           = aws_glue_connection.mysql[count.index].name
    "--S3_OUTPUT_PATH"                 = "s3://${aws_s3_bucket.data_lake.bucket}/${local.data_prefix}"
    "--RDS_DATABASE"                   = var.rds_database
  }

  execution_property {
    max_concurrent_runs = var.glue_max_concurrent_runs
  }

  tags = {
    Project = local.name
  }

  depends_on = [
    aws_s3_object.glue_entry_script,
    aws_s3_object.glue_modules_zip,
    aws_iam_role_policy.glue_etl_inline,
  ]
}
