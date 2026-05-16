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

variable "rds_endpoint" {
  type        = string
  description = "RDS endpoint hostname (without port)."
}

variable "rds_port" {
  type        = number
  description = "RDS port."
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

variable "vpc_id" {
  type        = string
  description = "VPC id for the Glue connection."
}

variable "subnet_id" {
  type        = string
  description = "Subnet id for the Glue connection."
}

variable "glue_sg_id" {
  type        = string
  description = "Security group id to attach to the Glue connection."
  default     = null
  nullable    = true
}

variable "glue_role_name" {
  type        = string
  description = "Existing IAM Role name to be used by Glue Job (lab environments often block iam:CreateRole)."
  default     = "LabRole"
}

