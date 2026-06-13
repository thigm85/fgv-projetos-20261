locals {
  bucket_name  = var.bucket_name != "" ? var.bucket_name : "${var.project_prefix}-${data.aws_caller_identity.current.account_id}"
  allowed_cidr = var.allowed_cidr != "" ? var.allowed_cidr : "${trimspace(data.http.public_ip.response_body)}/32"
  glue_role_arn = var.create_glue_role ? aws_iam_role.glue[0].arn : (
    var.existing_glue_role_arn != "" ? var.existing_glue_role_arn : data.aws_iam_role.existing_glue[0].arn
  )
}

data "aws_caller_identity" "current" {}

data "http" "public_ip" {
  url = "https://checkip.amazonaws.com/"
}

data "aws_iam_role" "existing_glue" {
  count = var.create_glue_role ? 0 : 1
  name  = var.existing_glue_role_name
}

data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

data "aws_route_tables" "default" {
  vpc_id = data.aws_vpc.default.id
}

data "aws_subnet" "selected" {
  id = data.aws_subnets.default.ids[0]
}

resource "aws_db_subnet_group" "classicmodels" {
  name       = "${var.project_prefix}-db-subnet-group"
  subnet_ids = data.aws_subnets.default.ids

  tags = {
    Name = "${var.project_prefix}-db-subnet-group"
  }
}

resource "aws_vpc_endpoint" "s3" {
  vpc_id          = data.aws_vpc.default.id
  service_name    = "com.amazonaws.${var.aws_region}.s3"
  route_table_ids = data.aws_route_tables.default.ids

  tags = {
    Name = "${var.project_prefix}-s3-endpoint"
  }
}

resource "aws_security_group" "rds" {
  name        = "${var.project_prefix}-rds-sg"
  description = "RDS access for local bootstrap and Glue"
  vpc_id      = data.aws_vpc.default.id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.project_prefix}-rds-sg"
  }
}

resource "aws_security_group_rule" "rds_local_ingress" {
  type              = "ingress"
  from_port         = var.db_port
  to_port           = var.db_port
  protocol          = "tcp"
  security_group_id = aws_security_group.rds.id
  cidr_blocks       = [local.allowed_cidr]
  description       = "Local MySQL access for lab bootstrap"
}

resource "aws_security_group" "glue" {
  name        = "${var.project_prefix}-glue-sg"
  description = "AWS Glue job networking"
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
  description              = "Glue self-referencing networking"
}

resource "aws_security_group_rule" "rds_from_glue" {
  type                     = "ingress"
  from_port                = var.db_port
  to_port                  = var.db_port
  protocol                 = "tcp"
  security_group_id        = aws_security_group.rds.id
  source_security_group_id = aws_security_group.glue.id
  description              = "Glue access to MySQL"
}

resource "aws_db_instance" "classicmodels" {
  identifier             = var.db_identifier
  allocated_storage      = 20
  max_allocated_storage  = 100
  db_name                = var.db_name
  engine                 = "mysql"
  engine_version         = var.db_engine_version
  instance_class         = "db.t3.micro"
  username               = var.db_username
  password               = var.db_password
  port                   = var.db_port
  publicly_accessible    = true
  skip_final_snapshot    = true
  deletion_protection    = false
  storage_encrypted      = false
  db_subnet_group_name   = aws_db_subnet_group.classicmodels.name
  vpc_security_group_ids = [aws_security_group.rds.id]

  tags = {
    Name = "${var.project_prefix}-mysql"
  }
}

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

resource "aws_s3_object" "glue_script" {
  bucket       = aws_s3_bucket.analytics.id
  key          = var.glue_script_key
  source       = "${path.module}/../glue/etl_job.py"
  etag         = filemd5("${path.module}/../glue/etl_job.py")
  content_type = "text/x-python"
}

resource "aws_iam_role" "glue" {
  count = var.create_glue_role ? 1 : 0
  name = "${var.project_prefix}-glue-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "glue.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "glue_service" {
  count      = var.create_glue_role ? 1 : 0
  role       = aws_iam_role.glue[0].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole"
}

resource "aws_iam_role_policy" "glue_s3_access" {
  count = var.create_glue_role ? 1 : 0
  name = "${var.project_prefix}-glue-s3-access"
  role = aws_iam_role.glue[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:ListBucket"
        ]
        Resource = [
          aws_s3_bucket.analytics.arn,
          "${aws_s3_bucket.analytics.arn}/*"
        ]
      }
    ]
  })
}

resource "aws_glue_connection" "classicmodels" {
  name = var.glue_connection_name

  connection_type = "JDBC"

  connection_properties = {
    JDBC_CONNECTION_URL = "jdbc:mysql://${aws_db_instance.classicmodels.address}:${var.db_port}/${var.db_name}"
    USERNAME            = var.db_username
    PASSWORD            = var.db_password
  }

  physical_connection_requirements {
    availability_zone      = data.aws_subnet.selected.availability_zone
    security_group_id_list = [aws_security_group.glue.id]
    subnet_id              = data.aws_subnet.selected.id
  }

  depends_on = [aws_vpc_endpoint.s3]
}

resource "aws_glue_job" "classicmodels" {
  name     = var.glue_job_name
  role_arn = local.glue_role_arn

  glue_version      = "4.0"
  max_retries       = 0
  timeout           = 30
  number_of_workers = 2
  worker_type       = "G.1X"

  command {
    name            = "glueetl"
    script_location = "s3://${aws_s3_bucket.analytics.bucket}/${aws_s3_object.glue_script.key}"
    python_version  = "3"
  }

  connections = [aws_glue_connection.classicmodels.name]

  default_arguments = {
    "--job-language"                         = "python"
    "--enable-continuous-cloudwatch-log"    = "true"
    "--enable-glue-datacatalog"             = "false"
    "--TempDir"                             = "s3://${aws_s3_bucket.analytics.bucket}/tmp/"
    "--db_host"                             = aws_db_instance.classicmodels.address
    "--db_port"                             = tostring(var.db_port)
    "--db_name"                             = var.db_name
    "--db_user"                             = var.db_username
    "--db_password"                         = var.db_password
    "--output_bucket"                       = aws_s3_bucket.analytics.bucket
    "--output_prefix"                       = "analytics"
  }

  depends_on = [
    aws_s3_object.glue_script,
    aws_iam_role_policy_attachment.glue_service,
    aws_iam_role_policy.glue_s3_access
  ]
}
