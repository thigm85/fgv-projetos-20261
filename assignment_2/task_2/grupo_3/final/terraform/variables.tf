variable "region" {
  description = "AWS region used to provision resources."
  type        = string
  default     = "us-east-1"
}

variable "db_name" {
  description = "Database name in the RDS instance."
  type        = string
  default     = "classicmodels"
}

variable "rds_host" {
  description = "RDS endpoint hostname without port."
  type        = string
}

variable "rds_port" {
  description = "RDS MySQL port."
  type        = number
  default     = 3306
}

variable "db_username" {
  description = "Database username used by Glue JDBC."
  type        = string
  default     = "admin"
}

variable "db_password" {
  description = "Database password used by Glue JDBC."
  type        = string
  sensitive   = true
}

variable "etl_bucket_name" {
  description = "S3 bucket name for Glue script, temp files and analytics outputs. Leave empty to use an account-based name."
  type        = string
  default     = ""
}

variable "glue_job_name" {
  description = "Glue incremental ETL job name."
  type        = string
  default     = "classicmodels-incremental-etl"
}

variable "glue_connection_name" {
  description = "Glue JDBC connection name."
  type        = string
  default     = "classicmodels-incremental-rds-connection"
}

variable "glue_database_name" {
  description = "Glue Catalog database exposed to Athena."
  type        = string
  default     = "classicmodels_analytics"
}

variable "glue_workers" {
  description = "Number of workers for the Glue job."
  type        = number
  default     = 2
}

variable "existing_glue_role_arn" {
  description = "Existing Glue role ARN, for example the lab LabRole. If empty, Terraform creates a role."
  type        = string
  default     = ""
}

variable "existing_glue_role_name" {
  description = "Existing Glue role name. Use with existing_glue_role_arn only for documentation/outputs."
  type        = string
  default     = ""
}

variable "existing_eventbridge_role_arn" {
  description = "Existing EventBridge role ARN allowed to call glue:StartJobRun. If empty, Terraform creates a role."
  type        = string
  default     = ""
}

variable "glue_subnet_id" {
  description = "Subnet used by the Glue JDBC connection. Leave empty only if the RDS is reachable without VPC connection requirements."
  type        = string
  default     = ""
}

variable "glue_security_group_id" {
  description = "Security group used by the Glue JDBC connection."
  type        = string
  default     = ""
}

variable "glue_availability_zone" {
  description = "Availability zone for the Glue JDBC connection, for example us-east-1a."
  type        = string
  default     = ""
}

variable "glue_vpc_id" {
  description = "VPC ID where the Glue connection subnet lives. Required to create the S3 Gateway VPC endpoint used by Glue."
  type        = string
  default     = ""
}

variable "glue_route_table_ids" {
  description = "Route table IDs associated with the Glue subnet. Required to create the S3 Gateway VPC endpoint used by Glue."
  type        = list(string)
  default     = []
}

variable "eventbridge_schedule_expression" {
  description = "EventBridge cron/rate expression used to trigger the incremental Glue job."
  type        = string
  default     = "cron(0 12 ? * MON *)"
}
