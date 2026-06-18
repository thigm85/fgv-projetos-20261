variable "aws_region" {
  description = "AWS region"
  type = string
  default = "us-east-1"
}

variable "project_name" {
  description = "Project name prefix for resource naming"
  type = string
  default = "classicmodels-etl"
}

variable "rds_instance_id" {
  description = "RDS instance identifier"
  type = string
  default = "db-classicmodels"
}

variable "rds_database" {
  description = "Database name in RDS"
  type = string
  default = "classicmodels"
}

variable "rds_username" {
  description = "RDS master username"
  type = string
  sensitive = true
}

variable "rds_password" {
  description = "RDS master password"
  type = string
  sensitive = true
}
