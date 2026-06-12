variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "bucket_name_prefix" {
  type    = string
  default = "tomas-classicmodels-task2"
}

variable "resource_name_prefix" {
  type    = string
  default = "tomas-classicmodels-task2"
}

variable "rds_instance_identifier" {
  type    = string
  default = "tomas-classicmodels-task2"
}

variable "db_username" {
  type    = string
  default = "admin"
}

variable "db_password" {
  type      = string
  sensitive = true
}

variable "db_name" {
  type    = string
  default = "classicmodels"
}

variable "glue_job_name" {
  type    = string
  default = "tomas-classicmodels-task2-incremental-etl"
}

variable "glue_database_name" {
  type    = string
  default = "tomas_classicmodels_task2_analytics"
}
