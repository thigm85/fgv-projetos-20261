variable "region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "db_identifier" {
  description = "RDS instance identifier"
  type        = string
  default     = "classicmodels-db"
}

variable "allocated_storage" {
  description = "Allocated storage in GB"
  type        = number
  default     = 20
}

variable "db_name" {
  description = "Database name"
  type        = string
  default     = "classicmodels"
}

variable "instance_class" {
  description = "RDS instance class"
  type        = string
  default     = "db.t3.micro"
}

variable "engine_version" {
  description = "MySQL engine version"
  type        = string
  default     = "8.0.40"
}

variable "username" {
  description = "Master username"
  type        = string
  default     = "admin"
}

variable "password" {
  description = "Master password"
  type        = string
  sensitive   = true
}

variable "s3_bucket_name" {
  description = "S3 bucket name for data lake"
  type        = string
  default     = "classicmodels-data-lake"
}

variable "glue_job_name" {
  description = "AWS Glue job name"
  type        = string
  default     = "classicmodels-etl"
}

variable "glue_database_name" {
  description = "Glue catalog database name"
  type        = string
  default     = "classicmodels"
}