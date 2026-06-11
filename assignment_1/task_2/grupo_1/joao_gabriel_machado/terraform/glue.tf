# =====================================================================
# BUCKET S3 
# =====================================================================
resource "aws_s3_bucket" "datalake" {
  bucket        = "fgv-datalake-joao-gabriel-9090"
  force_destroy = true
}

# =====================================================================
# IAM ROLE (LabRole nativa do Learner Lab)
# =====================================================================
data "aws_iam_role" "lab_role" {
  name = "LabRole"
}

# =====================================================================
# CONEXÃO DO GLUE COM O RDS
# =====================================================================
data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

resource "aws_glue_connection" "rds_conn" {
  name = "classicmodels-rds-conn"
  
  connection_properties = {
    JDBC_CONNECTION_URL = "jdbc:mysql://${aws_db_instance.sales_analytics.endpoint}/classicmodels"
    USERNAME            = var.db_user
    PASSWORD            = var.db_password
  }

  physical_connection_requirements {
    availability_zone      = aws_db_instance.sales_analytics.availability_zone
    security_group_id_list = [aws_security_group.rds_sg.id]
    subnet_id              = data.aws_subnets.default.ids[0]
  }
}

# =====================================================================
# UPLOAD DO SCRIPT E JOB DO GLUE 
# =====================================================================
resource "aws_s3_object" "glue_script" {
  bucket = aws_s3_bucket.datalake.id
  key    = "scripts/etl_job.py"
  source = "${path.module}/../sql/etl_job.py"

  etag   = filemd5("${path.module}/../sql/etl_job.py")
}

resource "aws_glue_job" "etl_job" {
  name     = "classicmodels-etl-job"
  
  # Aqui é onde passamos a usar a LabRole em vez da role que tentaríamos criar
  role_arn = data.aws_iam_role.lab_role.arn
  
  connections = [aws_glue_connection.rds_conn.name]
  
  command {
    script_location = "s3://${aws_s3_bucket.datalake.id}/${aws_s3_object.glue_script.key}"
    python_version  = "3"
  }
  
  default_arguments = {
    "--TempDir"             = "s3://${aws_s3_bucket.datalake.id}/temp/"
    "--job-bookmark-option" = "job-bookmark-disable"
    "--target_bucket"       = "s3://${aws_s3_bucket.datalake.id}/data/"
  }
  
  glue_version      = "4.0"
  worker_type       = "G.1X"
  number_of_workers = 2
}


# task 3
resource "aws_glue_catalog_database" "star_schema_db" {
  name        = "classicmodels_star_schema"
  description = "Database logico para o modelo estrela (Star Schema) via Athena"
}

resource "aws_glue_crawler" "parquet_crawler" {
  database_name = aws_glue_catalog_database.star_schema_db.name
  name          = "classicmodels-parquet-crawler"
  role          = data.aws_iam_role.lab_role.arn

  # Aponta para a pasta dos parquets
  s3_target {
    path = "s3://${aws_s3_bucket.datalake.id}/data/"
  }
}

resource "aws_s3_object" "athena_results" {
  bucket = aws_s3_bucket.datalake.id
  key    = "athena-results/"
}