variable "aws_region" {
  type        = string
  description = "AWS region."
  default     = "us-east-1"
}

variable "project_name" {
  type        = string
  description = "Name prefix for resources."
  default     = "classicmodels-etl-g4"
}

variable "rds_db_instance_identifier" {
  type        = string
  description = "RDS instance id from Task 1 (01_provision_rds.py); endpoint is resolved via data source."
  default     = "classicmodels-mysql-g4"
}

variable "rds_port" {
  type        = number
  description = "RDS port fallback if not returned by DescribeDBInstances."
  default     = 3306
}

variable "db_name" {
  type        = string
  description = "Database name (classicmodels)."
  default     = "classicmodels"
}

variable "db_user" {
  type        = string
  description = "DB username."
  default     = "admin"
}

variable "db_password" {
  type        = string
  description = "DB password."
  sensitive   = true
}

variable "glue_sg_id" {
  type        = string
  description = "Optional extra SG for Glue connection; default uses the RDS instance SG from discovery."
  default     = null
  nullable    = true
}

variable "glue_role_name" {
  type        = string
  description = "Existing IAM Role name to be used by Glue Job (lab environments often block iam:CreateRole)."
  default     = "LabRole"
}

variable "glue_database_name" {
  type        = string
  description = "Glue/Athena database name for star-schema tables."
  default     = "classicmodels_star_g4"
}

