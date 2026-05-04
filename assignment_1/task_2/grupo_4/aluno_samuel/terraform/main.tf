provider "aws" {
  region     = "us-east-1"  
}

resource "random_id" "rand" {
  byte_length = 4
}

resource "aws_s3_bucket" "data_lake" {
  bucket = "classicmodels-data-lake-g4-${random_id.rand.hex}"
}

resource "aws_glue_connection" "mysql_conn" {
  name = "classicmodels-mysql-connection"

  connection_properties = {
    JDBC_CONNECTION_URL = "jdbc:mysql://SEU_ENDPOINT:3306/classicmodels"
    USERNAME            = "admin"
    PASSWORD            = "SUA_SENHA"
  }

  physical_connection_requirements {
    availability_zone      = "us-east-1a"
    security_group_id_list = ["SEU_SECURITY_GROUP"]
    subnet_id              = "SEU_SUBNET_ID"
  }
}

resource "aws_glue_job" "etl_job" {
  name     = "classicmodels-etl"
  role_arn = "arn:aws:iam::114356001279:role/LabRole"

  command {
    script_location = "s3://${aws_s3_bucket.data_lake.bucket}/scripts/etl_script.py"
    python_version  = "3"
  }

  glue_version = "4.0"

  default_arguments = {
    "--TempDir" = "s3://${aws_s3_bucket.data_lake.bucket}/temp/"
    "--extra-jars" = "s3://aws-glue-jars-prod-us-east-1/tools/mysql-connector-java-8.0.30.jar"
  }

  max_retries = 0
}
