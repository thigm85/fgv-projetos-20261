variable "region" {
  description = "AWS region."
  type        = string
  default     = "us-east-1"
}

variable "db_name" {
  description = "Database name in the RDS instance."
  type        = string
  default     = "classicmodels"
}

variable "rds_host" {
  description = "RDS endpoint hostname (without port)."
  type        = string
}

variable "rds_port" {
  description = "RDS MySQL port."
  type        = number
  default     = 3306
}

variable "db_username" {
  description = "Database username for Glue JDBC."
  type        = string
  default     = "admin"
}

variable "db_password" {
  description = "Database password for Glue JDBC."
  type        = string
  sensitive   = true
}

variable "etl_bucket_name" {
  description = "S3 bucket name for the ETL pipeline. Leave empty to auto-generate from account ID + region."
  type        = string
  default     = ""
}

variable "glue_job_name" {
  description = "Name of the Glue incremental ETL job."
  type        = string
  default     = "classicmodels-incremental-etl"
}

variable "glue_connection_name" {
  description = "Name of the Glue JDBC connection."
  type        = string
  default     = "classicmodels-rds-connection"
}

variable "glue_database_name" {
  description = "Name of the Glue Catalog database exposed to Athena."
  type        = string
  default     = "classicmodels_analytics"
}

variable "glue_workers" {
  description = "Number of G.1X workers for the Glue job."
  type        = number
  default     = 2
}

variable "existing_glue_role_arn" {
  description = "ARN of an existing IAM role for Glue (e.g. LabRole). Leave empty to let Terraform create one."
  type        = string
  default     = ""
}

variable "existing_glue_role_name" {
  description = "Name of the existing Glue role (documentation only, used in outputs)."
  type        = string
  default     = ""
}

variable "existing_eventbridge_role_arn" {
  description = "ARN of an existing IAM role for EventBridge Scheduler. Leave empty to let Terraform create one."
  type        = string
  default     = ""
}

variable "glue_subnet_id" {
  description = "Subnet ID for the Glue JDBC connection. Required when RDS is in a private subnet."
  type        = string
  default     = ""
}

variable "glue_security_group_id" {
  description = "Security group ID for the Glue JDBC connection."
  type        = string
  default     = ""
}

variable "glue_availability_zone" {
  description = "Availability zone for the Glue JDBC connection (e.g. us-east-1a)."
  type        = string
  default     = ""
}

variable "glue_vpc_id" {
  description = "VPC ID where the Glue subnet lives. Required to create the S3 Gateway VPC endpoint."
  type        = string
  default     = ""
}

variable "glue_route_table_ids" {
  description = "Route table IDs for the S3 Gateway VPC endpoint."
  type        = list(string)
  default     = []
}

variable "eventbridge_schedule_expression" {
  description = "EventBridge Scheduler cron/rate expression for the weekly job trigger."
  type        = string
  default     = "cron(0 12 ? * MON *)"
}
