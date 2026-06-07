variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "bucket_name_prefix" {
  type    = string
  default = "classicmodels-analytics"
}

variable "db_username" {
  type    = string
  default = "admin"
}

variable "db_password" {
  type      = string
  sensitive = true
}

variable "db_name" {
  type    = string
  default = "classicmodels"
}

variable "glue_job_name" {
  type    = string
  default = "classicmodels-incremental-etl"
}

variable "lab_role_arn" {
  type        = string
  description = "ARN da LabRole do AWS Academy (ex: arn:aws:iam::123456789012:role/LabRole)"
}
