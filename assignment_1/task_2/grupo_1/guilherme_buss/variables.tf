variable "aws_region" {
  type        = string
  default     = "us-east-1"
}

variable "aws_profile" {
  type        = string
  default     = "default"
}

variable "project_name" {
  type        = string
  default     = "classic-models-etl"
}

variable "environment" {
  type        = string
  default     = "dev"
}

variable "rds_instance_identifier" {
  type        = string
  default     = "classic-models-db"
}

variable "rds_allocated_storage" {
  type        = number
  default     = 20
}

variable "rds_engine_version" {
  type        = string
  default     = "8.0.35"
}

variable "rds_instance_class" {
  type        = string
  default     = "db.t3.micro"
}

variable "db_name" {
  type        = string
  default     = "classicmodels"
}

variable "db_master_username" {
  type        = string
  default     = "admin"
}

variable "db_master_password" {
  type        = string
  sensitive   = true
  default     = "ClassicModels2024!"
}

variable "glue_job_name" {
  type        = string
  default     = "classic-models-etl-job"
}

variable "glue_job_worker_type" {
  type        = string
  default     = "G.1X"
}

variable "glue_job_num_workers" {
  type        = number
  default     = 2
}

variable "s3_bucket_name" {
  type        = string
  default     = ""
}

variable "tags" {
  type        = map(string)
  default = {
    Project = "ClassicModels-ETL"
    ManagedBy = "Terraform"
    Purpose = "DataEngineering"
  }
}

variable "enable_rds_public_access" {
  type        = bool
  default     = true
}

variable "vpc_id" {
  type        = string
  default     = ""
}

variable "private_subnet_ids" {
  type        = list(string)
  default     = []
}