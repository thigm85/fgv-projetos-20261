# --- S3 ---

resource "aws_s3_bucket" "data_lake" {
  bucket        = var.s3_bucket_name
  force_destroy = true

  tags = { Name = var.s3_bucket_name }
}

resource "aws_s3_object" "glue_script" {
  bucket = aws_s3_bucket.data_lake.id
  key    = "scripts/glue_etl.py"
  source = "${path.module}/glue_etl.py"
  etag   = filemd5("${path.module}/glue_etl.py")
}

# --- IAM Role ---
# O AWS Academy não permite criar roles via API.
# Usa a LabRole pré-existente fornecida pelo lab.

data "aws_iam_role" "lab_role" {
  name = "LabRole"
}

# --- Security Group do Glue ---

resource "aws_security_group" "glue" {
  name        = "glue-classicmodels-sg"
  description = "Glue ETL job security group"
  vpc_id      = data.aws_vpc.default.id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "glue-classicmodels-sg" }
}

# Regra self-referencing obrigatória pelo Glue para comunicação interna
resource "aws_security_group_rule" "glue_self" {
  type              = "ingress"
  from_port         = 0
  to_port           = 65535
  protocol          = "tcp"
  self              = true
  security_group_id = aws_security_group.glue.id
}

# --- Glue Connection para o RDS ---

resource "aws_glue_connection" "rds" {
  name            = "classicmodels-rds-connection"
  connection_type = "JDBC"

  connection_properties = {
    JDBC_CONNECTION_URL = "jdbc:mysql://${aws_db_instance.classicmodels.address}:${aws_db_instance.classicmodels.port}/classicmodels?useSSL=false&allowPublicKeyRetrieval=true"
    USERNAME            = var.rds_admin_user
    PASSWORD            = var.rds_admin_password
    JDBC_ENFORCE_SSL    = "false"
  }

  physical_connection_requirements {
    availability_zone      = data.aws_subnet.glue.availability_zone
    subnet_id              = data.aws_subnet.glue.id
    security_group_id_list = [aws_security_group.glue.id]
  }
}

# --- Glue Job ---

resource "aws_glue_job" "etl" {
  name     = "classicmodels-etl-job"
  role_arn = data.aws_iam_role.lab_role.arn

  command {
    name            = "glueetl"
    script_location = "s3://${aws_s3_bucket.data_lake.id}/scripts/glue_etl.py"
    python_version  = "3"
  }

  default_arguments = {
    "--job-language"                     = "python"
    "--enable-metrics"                   = "true"
    "--enable-continuous-cloudwatch-log" = "true"
    "--TempDir"                          = "s3://${aws_s3_bucket.data_lake.id}/tmp/"
    "--RDS_ENDPOINT"                     = aws_db_instance.classicmodels.address
    "--RDS_PORT"                         = tostring(aws_db_instance.classicmodels.port)
    "--RDS_USERNAME"                     = var.rds_admin_user
    "--RDS_PASSWORD"                     = var.rds_admin_password
    "--RDS_DB_NAME"                      = "classicmodels"
    "--S3_OUTPUT_PATH"                   = "s3://${aws_s3_bucket.data_lake.id}/data/"
  }

  connections = [aws_glue_connection.rds.name]

  glue_version      = "4.0"
  number_of_workers = 2
  worker_type       = "G.1X"
  timeout           = 30

  tags = { Name = "classicmodels-etl-job" }
}
