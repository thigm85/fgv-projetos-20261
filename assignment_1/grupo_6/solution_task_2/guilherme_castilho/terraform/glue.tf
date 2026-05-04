# S3 Bucket para armazenar os dados Parquet e os scripts
resource "aws_s3_bucket" "datalake" {
  bucket_prefix = "datalake-classicmodels-"
  force_destroy = true
}

# Busca a Role já existente no ambiente de laboratório (Cenário 1)
data "aws_iam_role" "lab_role" {
  # IMPORTANTE: Se o seu laboratório usar um nome diferente, 
  # como "vvoc-role" ou "vocareare-role", altere aqui.
  name = "LabRole" 
}

# Conexão do Glue com o RDS
resource "aws_glue_connection" "rds_conn" {
  name = "classicmodels-rds-conn"
  connection_properties = {
    JDBC_CONNECTION_URL = "jdbc:mysql://${aws_db_instance.mysql_source.endpoint}/${var.db_name}"
    USERNAME            = var.db_username
    PASSWORD            = var.db_password
  }

  physical_connection_requirements {
    availability_zone      = aws_db_instance.mysql_source.availability_zone
    security_group_id_list = [aws_security_group.rds_sg.id]
    
    # Agora aponta para a sub-rede que filtramos acima
    subnet_id              = tolist(data.aws_subnets.rds_subnet.ids)[0]
  }
}

# Envio do script ETL para o S3
resource "aws_s3_object" "etl_script" {
  bucket = aws_s3_bucket.datalake.id
  key    = "scripts/etl_job.py"
  source = "../scripts/etl_job.py"
  etag   = filemd5("../scripts/etl_job.py")
}

# Definição do Job do AWS Glue usando a LabRole
resource "aws_glue_job" "etl_job" {
  name     = "classicmodels-etl"
  role_arn = data.aws_iam_role.lab_role.arn
  connections = [aws_glue_connection.rds_conn.name]

  command {
    script_location = "s3://${aws_s3_bucket.datalake.id}/${aws_s3_object.etl_script.key}"
    python_version  = "3"
  }

  default_arguments = {
    "--job-language"        = "python"
    "--S3_TARGET_PATH"      = "s3://${aws_s3_bucket.datalake.id}/output/"
    "--CONNECTION_NAME"     = aws_glue_connection.rds_conn.name
    "--DB_NAME"             = var.db_name
  }

  glue_version = "4.0"
  worker_type  = "G.1X"
  number_of_workers = 2
}

output "s3_datalake_bucket" {
  value = aws_s3_bucket.datalake.bucket
}

# Coleta informações da rede padrão (VPC) e subnets
data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "rds_subnet" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
  filter {
    name   = "availability-zone"
    # Pega a AZ exata onde o RDS foi provisionado
    values = [aws_db_instance.mysql_source.availability_zone] 
  }
}

data "aws_route_tables" "default" {
  vpc_id = data.aws_vpc.default.id
}

# Cria o endpoint para o S3
resource "aws_vpc_endpoint" "s3" {
  vpc_id          = data.aws_vpc.default.id
  service_name    = "com.amazonaws.${var.aws_region}.s3"
  route_table_ids = data.aws_route_tables.default.ids
}