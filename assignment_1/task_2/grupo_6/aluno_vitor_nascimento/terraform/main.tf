provider "aws" {
  region = "us-east-1"
}

variable "db_password" {
  description = "Senha do banco de dados RDS"
  type        = string
  sensitive   = true
}

variable "db_username" {
  description = "Username do banco de dados RDS"
  type        = string
  sensitive   = true
}

variable "db_name" {
  description = "Nome do banco de dados"
  type        = string
  default     = "classicmodels"
}

data "http" "my_ip" {
  url = "https://checkip.amazonaws.com/"
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

resource "aws_security_group" "rds_sg" {
  name_prefix = "rds-sg-task2-"
  description = "Permitir trafego MySQL e comunicacao Glue"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    from_port   = 3306
    to_port     = 3306
    protocol    = "tcp"
    cidr_blocks = ["${chomp(data.http.my_ip.response_body)}/32"]
    description = "Acesso restrito ao IP do desenvolvedor"
  }

  ingress {
    from_port = 0
    to_port   = 65535
    protocol  = "tcp"
    self      = true
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_vpc_endpoint" "s3" {
  vpc_id            = data.aws_vpc.default.id
  service_name      = "com.amazonaws.us-east-1.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [data.aws_vpc.default.main_route_table_id]
}

resource "aws_db_instance" "mysql_task" {
  allocated_storage      = 10
  engine                 = "mysql"
  engine_version         = "8.0"
  instance_class         = "db.t3.micro"
  username               = var.db_username
  password               = var.db_password
  parameter_group_name   = "default.mysql8.0"
  skip_final_snapshot    = true
  publicly_accessible    = true
  vpc_security_group_ids = [aws_security_group.rds_sg.id]
}

resource "aws_s3_bucket" "datalake" {
  bucket_prefix = "fgv-datalake-vitor-"
  force_destroy = true
}

resource "aws_s3_object" "glue_script" {
  bucket = aws_s3_bucket.datalake.id
  key    = "scripts/glue_etl.py"
  source = "../src/glue_etl.py"
  etag   = filemd5("../src/glue_etl.py")
}

data "aws_iam_role" "lab_role" {
  name = "LabRole"
}

resource "aws_glue_connection" "rds_connection" {
  name = "rds-mysql-connection"

  connection_properties = {
    JDBC_CONNECTION_URL = "jdbc:mysql://${aws_db_instance.mysql_task.endpoint}/${var.db_name}"
    PASSWORD            = var.db_password
    USERNAME            = var.db_username
  }

  physical_connection_requirements {
    availability_zone      = aws_db_instance.mysql_task.availability_zone
    security_group_id_list = [aws_security_group.rds_sg.id]
    subnet_id              = data.aws_subnets.default.ids[0]
  }
}

resource "aws_glue_job" "etl_job" {
  name     = "rds-to-s3-star-schema"
  role_arn = data.aws_iam_role.lab_role.arn
  glue_version = "4.0"
  worker_type  = "G.1X"
  number_of_workers = 2

  command {
    script_location = "s3://${aws_s3_bucket.datalake.id}/${aws_s3_object.glue_script.key}"
    python_version  = "3"
  }

  default_arguments = {
    "--job-language"        = "python"
    "--RDS_CONNECTION_NAME" = aws_glue_connection.rds_connection.name
    "--S3_OUTPUT_PATH"      = "s3://${aws_s3_bucket.datalake.id}/transformed_data"
    "--DB_NAME"             = var.db_name
    "--enable-metrics"      = "true"
    "--enable-continuous-cloudwatch-log" = "true"
  }

  connections = [aws_glue_connection.rds_connection.name]
}

output "rds_endpoint" {
  value = aws_db_instance.mysql_task.endpoint
}

output "s3_bucket" {
  value = aws_s3_bucket.datalake.id
}

output "glue_job_name" {
  value = aws_glue_job.etl_job.name
}
