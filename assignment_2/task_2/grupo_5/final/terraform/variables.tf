variable "aws_region" {
  description = "AWS region for all resources"
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Project prefix for resource naming"
  type        = string
  default     = "grupo5-a2-task2"
}

variable "db_host" {
  description = "RDS endpoint hostname (Assignment 1)"
  type        = string
}

variable "db_port" {
  description = "RDS MySQL port"
  type        = number
  default     = 3306
}

variable "db_name" {
  description = "Source database name"
  type        = string
  default     = "classicmodels"
}

variable "db_user" {
  description = "RDS username"
  type        = string
}

variable "db_password" {
  description = "RDS password"
  type        = string
  sensitive   = true
}

variable "db_security_group_id" {
  description = "Security group attached to the RDS instance"
  type        = string
}

variable "vpc_id" {
  description = "VPC where Glue network artifacts will be created"
  type        = string
}

variable "subnet_id" {
  description = "Subnet for Glue connection ENI (must belong to vpc_id, same VPC as RDS)"
  type        = string
}

variable "glue_role_arn" {
  description = "Existing IAM role ARN for AWS Glue (Learner Lab LabRole)"
  type        = string
}

variable "eventbridge_schedule" {
  description = "Cron expression for incremental ETL (UTC)"
  type        = string
  default     = "cron(0 12 ? * MON *)"
}
