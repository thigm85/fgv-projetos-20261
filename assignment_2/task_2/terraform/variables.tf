# ============================================================================
# Variables for Assignment 2 — Task 2: Incremental ETL
# ============================================================================

variable "aws_region" {
  type        = string
  default     = "us-east-1"
  description = "AWS region for all resources"
}

variable "aws_profile" {
  type        = string
  default     = "default"
  description = "AWS CLI profile to use"
}

variable "project_name" {
  type        = string
  default     = "classic-models-etl"
  description = "Project name prefix for resource naming"
}

# ---------------------------------------------------------------------------
# RDS / Database
# ---------------------------------------------------------------------------

variable "rds_endpoint" {
  type        = string
  description = "RDS endpoint (host:port) from Assignment 1. Example: classic-models-db.xxxxx.us-east-1.rds.amazonaws.com:3306"
}

variable "db_name" {
  type        = string
  default     = "classicmodels"
  description = "Database name on the RDS instance"
}

variable "db_master_username" {
  type        = string
  default     = "admin"
  description = "Master username for RDS"
}

variable "db_master_password" {
  type        = string
  sensitive   = true
  description = "Master password for RDS. Pass via TF_VAR_db_master_password env var — NEVER commit this."
}

# ---------------------------------------------------------------------------
# S3
# ---------------------------------------------------------------------------

variable "s3_bucket_name" {
  type        = string
  description = "Name of the existing S3 bucket from Assignment 1"
}

variable "s3_output_prefix" {
  type        = string
  default     = "output/"
  description = "S3 prefix for ETL output (must match A1 output path)"
}

# ---------------------------------------------------------------------------
# Secrets Manager
# ---------------------------------------------------------------------------

variable "rds_secret_name" {
  type        = string
  default     = "classic-models-etl/rds-credentials"
  description = "Name of the Secrets Manager secret created in A1"
}

# ---------------------------------------------------------------------------
# Glue
# ---------------------------------------------------------------------------

variable "glue_job_name" {
  type        = string
  default     = "classic-models-incremental-etl-job"
  description = "Name for the new incremental Glue job"
}

variable "glue_connection_name" {
  type        = string
  default     = "classic-models-etl-rds-connection"
  description = "Name of the existing Glue JDBC connection from A1"
}

variable "glue_worker_type" {
  type        = string
  default     = "G.1X"
  description = "Glue worker type"
}

variable "glue_num_workers" {
  type        = number
  default     = 2
  description = "Number of Glue workers"
}

variable "glue_catalog_database" {
  type        = string
  default     = "classicmodels_analytics"
  description = "Glue Catalog database name for Athena queries"
}

# ---------------------------------------------------------------------------
# EventBridge / Scheduling
# ---------------------------------------------------------------------------

variable "schedule_expression" {
  type        = string
  default     = "cron(0 12 ? * MON *)"
  description = "EventBridge cron expression for scheduled execution (default: weekly Monday at 12:00 UTC)"
}

variable "schedule_enabled" {
  type        = bool
  default     = true
  description = "Whether the EventBridge schedule is enabled"
}

# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------

variable "tags" {
  type        = map(string)
  default = {
    Project     = "ClassicModels-ETL"
    ManagedBy   = "Terraform"
    Purpose     = "DataEngineering"
    Assignment  = "A2-Task2"
    Environment = "dev"
  }
}
