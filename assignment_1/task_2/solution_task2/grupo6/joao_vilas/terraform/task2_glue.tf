data "aws_caller_identity" "current" {}

data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

data "aws_subnet" "glue_subnet" {
  id = data.aws_subnets.default.ids[0]
}

data "aws_route_tables" "default" {
  vpc_id = data.aws_vpc.default.id
}

data "aws_iam_role" "existing_glue_role" {
  count = var.use_existing_lab_role ? 1 : 0
  name  = var.existing_glue_role_name
}

locals {
  etl_bucket_name = "${var.project_prefix}-${data.aws_caller_identity.current.account_id}-${var.aws_region}"
  glue_script_key = "glue-scripts/etl_classicmodels_star_schema.py"
  output_prefix   = "curated/classicmodels"

  glue_role_arn = var.use_existing_lab_role ? data.aws_iam_role.existing_glue_role[0].arn : aws_iam_role.glue_role[0].arn
}

resource "aws_s3_bucket" "etl_bucket" {
  bucket        = local.etl_bucket_name
  force_destroy = true

  tags = {
    Project = "classicmodels-task2"
    Owner   = "grupo6-joao-vilas"
  }
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

resource "aws_vpc_endpoint" "s3" {
  vpc_id            = data.aws_vpc.default.id
  service_name      = "com.amazonaws.${var.aws_region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = data.aws_route_tables.default.ids

  tags = {
    Name    = "${var.project_prefix}-s3-endpoint"
    Project = "classicmodels-task2"
  }
}

resource "aws_security_group" "glue_sg" {
  name        = "${var.project_prefix}-glue-sg"
  description = "Security Group do AWS Glue para acessar RDS MySQL"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description = "Self-reference para comunicacao interna do Glue"
    from_port   = 0
    to_port     = 65535
    protocol    = "tcp"
    self        = true
  }

  egress {
    description = "Saida liberada para RDS, S3 endpoint e servicos AWS"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name    = "${var.project_prefix}-glue-sg"
    Project = "classicmodels-task2"
  }
}

resource "aws_security_group_rule" "rds_from_glue" {
  type                     = "ingress"
  description              = "Permite MySQL somente a partir do Glue"
  from_port                = 3306
  to_port                  = 3306
  protocol                 = "tcp"
  security_group_id        = aws_security_group.rds_sg.id
  source_security_group_id = aws_security_group.glue_sg.id
}

data "aws_iam_policy_document" "glue_assume_role" {
  count = var.use_existing_lab_role ? 0 : 1

  statement {
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["glue.amazonaws.com"]
    }

    actions = ["sts:AssumeRole"]
  }
}

resource "aws_iam_role" "glue_role" {
  count = var.use_existing_lab_role ? 0 : 1

  name               = "${var.project_prefix}-glue-role"
  assume_role_policy = data.aws_iam_policy_document.glue_assume_role[0].json

  tags = {
    Project = "classicmodels-task2"
  }
}

resource "aws_iam_role_policy_attachment" "glue_service_role" {
  count = var.use_existing_lab_role ? 0 : 1

  role       = aws_iam_role.glue_role[0].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole"
}

data "aws_iam_policy_document" "glue_s3_policy" {
  count = var.use_existing_lab_role ? 0 : 1

  statement {
    sid    = "AllowGlueBucketAccess"
    effect = "Allow"

    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:ListBucket"
    ]

    resources = [
      aws_s3_bucket.etl_bucket.arn,
      "${aws_s3_bucket.etl_bucket.arn}/*"
    ]
  }
}

resource "aws_iam_role_policy" "glue_s3_policy" {
  count = var.use_existing_lab_role ? 0 : 1

  name   = "${var.project_prefix}-glue-s3-policy"
  role   = aws_iam_role.glue_role[0].id
  policy = data.aws_iam_policy_document.glue_s3_policy[0].json
}

resource "aws_s3_object" "glue_script" {
  bucket = aws_s3_bucket.etl_bucket.id
  key    = local.glue_script_key
  source = "${path.module}/../glue/etl_classicmodels_star_schema.py"
  etag   = filemd5("${path.module}/../glue/etl_classicmodels_star_schema.py")
}

resource "aws_glue_connection" "classicmodels_mysql" {
  name            = "${var.project_prefix}-classicmodels-mysql"
  connection_type = "JDBC"

  connection_properties = {
    JDBC_CONNECTION_URL = "jdbc:mysql://${aws_db_instance.classicmodels_db.address}:${aws_db_instance.classicmodels_db.port}/${var.db_name}"
    USERNAME            = var.db_username
    PASSWORD            = var.db_password
  }

  physical_connection_requirements {
    availability_zone      = data.aws_subnet.glue_subnet.availability_zone
    security_group_id_list = [aws_security_group.glue_sg.id]
    subnet_id              = data.aws_subnet.glue_subnet.id
  }
}

resource "aws_glue_job" "classicmodels_etl" {
  name              = "${var.project_prefix}-classicmodels-etl"
  role_arn          = local.glue_role_arn
  glue_version      = "4.0"
  worker_type       = "G.1X"
  number_of_workers = 2
  timeout           = 30
  max_retries       = 0

  connections = [
    aws_glue_connection.classicmodels_mysql.name
  ]

  command {
    name            = "glueetl"
    script_location = "s3://${aws_s3_bucket.etl_bucket.bucket}/${local.glue_script_key}"
    python_version  = "3"
  }

  default_arguments = {
    "--job-language"                     = "python"
    "--connection_name"                  = aws_glue_connection.classicmodels_mysql.name
    "--output_s3_path"                   = "s3://${aws_s3_bucket.etl_bucket.bucket}/${local.output_prefix}"
    "--TempDir"                          = "s3://${aws_s3_bucket.etl_bucket.bucket}/glue-temp/"
    "--enable-metrics"                   = "true"
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-spark-ui"                  = "true"
    "--spark-event-logs-path"            = "s3://${aws_s3_bucket.etl_bucket.bucket}/spark-history/"
  }

  depends_on = [
    aws_s3_object.glue_script,
    aws_security_group_rule.rds_from_glue,
    aws_vpc_endpoint.s3
  ]

  tags = {
    Project = "classicmodels-task2"
  }
}