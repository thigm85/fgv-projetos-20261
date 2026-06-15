resource "aws_security_group" "glue_sg" {
  name        = "${var.project_prefix}-glue-sg"
  description = "Security Group do AWS Glue (self-ref para Spark + saida liberada)"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description = "Self-reference para comunicacao interna do Glue"
    from_port   = 0
    to_port     = 65535
    protocol    = "tcp"
    self        = true
  }

  egress {
    description = "Saida liberada para RDS, S3, Secrets Manager e demais APIs AWS"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_glue_connection" "classicmodels_mysql" {
  name            = "${var.project_prefix}-classicmodels-mysql"
  connection_type = "JDBC"

  connection_properties = {
    JDBC_CONNECTION_URL = "jdbc:mysql://${aws_db_instance.classicmodels_db.address}:${aws_db_instance.classicmodels_db.port}/${var.db_name}"
    USERNAME            = var.db_username
    PASSWORD            = random_password.db_password.result
  }

  physical_connection_requirements {
    availability_zone      = data.aws_subnet.glue_subnet.availability_zone
    security_group_id_list = [aws_security_group.glue_sg.id]
    subnet_id              = data.aws_subnet.glue_subnet.id
  }
}

resource "aws_glue_job" "classicmodels_etl" {
  name              = "${var.project_prefix}-classicmodels-etl"
  role_arn          = local.lab_role_arn
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
    aws_vpc_endpoint.s3,
  ]
}

resource "aws_glue_catalog_database" "classicmodels" {
  name        = var.glue_database_name
  description = "Star schema do classicmodels servindo o Athena na Task 3"
}

resource "aws_glue_catalog_table" "tables" {
  for_each = local.fact_tables

  database_name = aws_glue_catalog_database.classicmodels.name
  name          = each.key
  table_type    = "EXTERNAL_TABLE"

  parameters = {
    EXTERNAL              = "TRUE"
    classification        = "parquet"
    "parquet.compression" = "SNAPPY"
    "has_encrypted_data"  = "false"
  }

  storage_descriptor {
    location      = "s3://${aws_s3_bucket.etl_bucket.bucket}/${local.output_prefix}/${each.key}/"
    input_format  = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"

    ser_de_info {
      name                  = "ParquetHiveSerDe"
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
      parameters = {
        "serialization.format" = "1"
      }
    }

    dynamic "columns" {
      for_each = each.value.columns
      content {
        name = columns.value.name
        type = columns.value.type
      }
    }
  }
}
