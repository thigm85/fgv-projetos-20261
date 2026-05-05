provider "aws" {
  region = "us-east-1"
}

# Busca a rede padrão
data "aws_vpc" "default" { default = true }
data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}
data "aws_subnet" "first" { id = data.aws_subnets.default.ids[0] }
data "aws_route_tables" "vpc_routes" { vpc_id = data.aws_vpc.default.id }

# Busca os recursos da task 1
data "aws_security_group" "rds_sg" { name = "classicmodels-sg" }
data "aws_db_instance" "rds" { db_instance_identifier = "classicmodels-instance" }

# Permissão do AWS Learner Lab
data "aws_iam_role" "lab_role" { name = "LabRole" }

# Gera um ID aleatório para evitar nomes de buckets duplicados
resource "random_id" "bucket_suffix" { byte_length = 4 }

resource "aws_s3_bucket" "datalake" {
  bucket        = "classicmodels-lake-${random_id.bucket_suffix.hex}"
  force_destroy = true
}

resource "aws_vpc_endpoint" "s3_gateway" {
  vpc_id            = data.aws_vpc.default.id
  service_name      = "com.amazonaws.us-east-1.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = data.aws_route_tables.vpc_routes.ids
}

resource "aws_s3_object" "etl_script" {
  bucket = aws_s3_bucket.datalake.bucket
  key    = "scripts/etl_script.py"
  source = "${path.module}/etl_script.py"
  etag   = filemd5("${path.module}/etl_script.py")
}

resource "aws_glue_connection" "rds_conn" {
  name = "classicmodels-glue-conn"
  connection_properties = {
    # Pega o endpoint automaticamente da Task 1
    JDBC_CONNECTION_URL = "jdbc:mysql://${data.aws_db_instance.rds.endpoint}/classicmodels"
    USERNAME            = "admin"
    PASSWORD            =  var.db_password
  }

  physical_connection_requirements {
    availability_zone      = data.aws_subnet.first.availability_zone
    security_group_id_list = [data.aws_security_group.rds_sg.id]
    subnet_id              = data.aws_subnet.first.id
  }
}

resource "aws_glue_job" "etl_job" {
  name        = "classicmodels-star-schema-job"
  role_arn    = data.aws_iam_role.lab_role.arn
  connections = [aws_glue_connection.rds_conn.name]

  command {
    name            = "glueetl"
    script_location = "s3://${aws_s3_bucket.datalake.bucket}/${aws_s3_object.etl_script.key}"
    python_version  = "3"
  }

  default_arguments = {
    "--job-language"    = "python"
    "--TempDir"         = "s3://${aws_s3_bucket.datalake.bucket}/temp/"
    "--TARGET_BUCKET"   = aws_s3_bucket.datalake.bucket
    "--CONNECTION_NAME" = aws_glue_connection.rds_conn.name
  }

  glue_version      = "4.0"
  worker_type       = "G.1X"
  number_of_workers = 2
}

output "s3_bucket_name" {
  value = aws_s3_bucket.datalake.bucket
}

# Exporta o nome do bucket para o Python consumir automaticamente
resource "local_file" "bucket_name_export" {
  content  = aws_s3_bucket.datalake.bucket
  filename = "${path.module}/bucket_name.txt"
}