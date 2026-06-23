variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "rds_endpoint" {
  description = "RDS MySQL endpoint (from Task 1)"
  type        = string
}

variable "rds_db_name" {
  description = "RDS database name"
  type        = string
  default     = "classicmodels"
}

variable "rds_username" {
  description = "RDS admin username"
  type        = string
}

variable "rds_password" {
  description = "RDS admin password"
  type        = string
  sensitive   = true
}

variable "rds_port" {
  description = "RDS port"
  type        = number
  default     = 3306
}

variable "rds_subnet_ids" {
  description = "List of subnet IDs where RDS is deployed (from Task 1)"
  type        = list(string)
}

variable "rds_security_group_id" {
  description = "Security group ID of the RDS instance (from Task 1)"
  type        = string
}

variable "s3_bucket_name" {
  description = "Name of the S3 bucket for transformed data (must be globally unique)"
  type        = string
  default     = "classicmodels-datalake"
}

variable "glue_job_name" {
  description = "Name of the AWS Glue ETL job"
  type        = string
  default     = "classicmodels-etl-job"
}

variable "glue_connection_name" {
  description = "Name of the AWS Glue connection to RDS"
  type        = string
  default     = "classicmodels-rds-connection"
}
