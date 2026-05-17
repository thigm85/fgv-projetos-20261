provider "aws" {
  region = "us-east-1"
}

/* Variáveis para salvar user e password do banco */
variable "db_username" {
  type    = string
  default = "admin_user"
}

variable "db_password" {
  type      = string
  sensitive = true
}

/* Variável para liberar o banco só para o IP atual (para poder popular ele) */
data "http" "myip" {
  url = "http://ipv4.icanhazip.com"
}

/* Variável com a role IAM padrão do lab, já que não tem como criar roles no lab */
data "aws_iam_role" "lab_role" {
  name = "LabRole"
}

/* Configura VPC e subnet pro Glue poder acessar o banco e o S3*/
data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

data "aws_subnet" "selected" {
  id = data.aws_subnets.default.ids[0]
}

data "aws_region" "current" {}

data "aws_route_tables" "default" {
  vpc_id = data.aws_vpc.default.id
}

/* Criando security group que fala com a internet pro banco */

resource "aws_security_group" "dumb_sg" {
  name   = "public security group"
  vpc_id = data.aws_vpc.default.id

  /* Libera só o IP atual para escrever no banco */
  ingress {
    from_port   = 3306
    to_port     = 3306
    protocol    = "tcp"
    cidr_blocks = ["${chomp(data.http.myip.response_body)}/32"]
  }

  /* Aqui o self = true serve para o SG poder falar com ele mesmo, importante 
  pro Glue poder acessar o banco MySQL */
  ingress {
    from_port = 0
    to_port   = 0
    protocol  = "-1"
    self      = true
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

/* cria o banco de dados */

resource "aws_db_instance" "cars_database" {
  identifier             = "classicmodels-db"
  allocated_storage      = 10
  apply_immediately      = true
  db_name                = "classicmodels"
  engine                 = "mysql"
  engine_version         = "8.0"
  instance_class         = "db.t3.micro"
  username               = var.db_username
  password               = var.db_password
  parameter_group_name   = "default.mysql8.0"
  port                   = 3306
  publicly_accessible    = true
  skip_final_snapshot    = true
  vpc_security_group_ids = [aws_security_group.dumb_sg.id]
}

/* cria o bucket do S3 e já define como vai ser o upload do ETL nele*/
resource "aws_s3_bucket" "datalake_bucket" {
  bucket_prefix = "classicmodels-datalake-"
}

resource "aws_s3_object" "glue_script" {
  bucket = aws_s3_bucket.datalake_bucket.id
  key    = "scripts/glue_etl.py"
  source = "../glue_etl.py"
  etag   = filemd5("../glue_etl.py")
}

/* define como o glue vai ler o banco, formatando uma string para conexão com
o banco*/
resource "aws_glue_connection" "rds_conn" {
  name = "classicmodels_rds_connection"
  connection_properties = {
    JDBC_CONNECTION_URL = "jdbc:mysql://${aws_db_instance.cars_database.endpoint}/classicmodels"
    PASSWORD            = var.db_password
    USERNAME            = var.db_username
  }
  physical_connection_requirements {
    security_group_id_list = [aws_security_group.dumb_sg.id]
    subnet_id              = data.aws_subnets.default.ids[0]
  availability_zone      = data.aws_subnet.selected.availability_zone
  }
}

/* Define o Job do Glue */
resource "aws_glue_job" "etl_job" {
  name        = "classicmodels_etl_to_star_schema"
  role_arn    = data.aws_iam_role.lab_role.arn
  connections = [aws_glue_connection.rds_conn.name]

  command {
    script_location = "s3://${aws_s3_bucket.datalake_bucket.id}/scripts/glue_etl.py"
    python_version  = "3"
  }

  default_arguments = {
    "--TARGET_S3_PATH" = "s3://${aws_s3_bucket.datalake_bucket.id}/output/"
  }

  glue_version      = "4.0"
  worker_type       = "G.1X"
  number_of_workers = 2
}

resource "aws_vpc_endpoint" "s3_endpoint" {
  vpc_id            = data.aws_vpc.default.id
  service_name      = "com.amazonaws.${data.aws_region.current.name}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = data.aws_route_tables.default.ids
}

/* Define o nome do endpoint do RDS como output do terraform, bom para permitir
a leitura do endpoint depois*/
output "db_endpoint" {
  description = "O endpoint de conexao do banco de dados"
  value       = aws_db_instance.cars_database.endpoint
}

/* Define o nome do bucket do S3 como output do terraform, bom para permitir
a leitura dele depois*/
output "datalake_bucket" {
  description = "O nome do bucket do Data Lake"
  value       = aws_s3_bucket.datalake_bucket.id
}
