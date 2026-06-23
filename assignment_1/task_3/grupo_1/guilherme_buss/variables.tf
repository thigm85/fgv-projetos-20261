variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "aws_profile" {
  description = "AWS profile to use"
  type        = string
  default     = "default"
}

variable "project_name" {
  description = "Project name for resource naming"
  type        = string
  default     = "classic-models"
}

variable "tags" {
  description = "Common tags for all resources"
  type        = map(string)
  default = {
    Project     = "ClassicModels"
    Environment = "Development"
    Task        = "Task3-Analytics"
  }
}

variable "glue_database_name" {
  description = "Name of the Glue Catalog database containing the star schema tables from Task 2"
  type        = string
}

variable "athena_output_bucket" {
  description = "S3 bucket name for Athena query results (leave empty to auto-generate)"
  type        = string
  default     = ""
}

variable "athena_output_prefix" {
  description = "S3 prefix/path within the bucket for Athena query results"
  type        = string
  default     = "athena-results/"
}
