variable "aws_region" {
  description = "AWS region for all resources"
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Project prefix for resource naming"
  type        = string
  default     = "grupo5-task2"
}

variable "db_host" {
  description = "RDS endpoint hostname"
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
  description = "Subnet for Glue connection ENI (must belong to vpc_id)"
  type        = string
}

variable "glue_role_arn" {
  description = "Existing IAM role ARN for AWS Glue (Learner Lab managed role)"
  type        = string
}
