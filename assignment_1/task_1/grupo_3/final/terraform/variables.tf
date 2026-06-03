variable "region" {
  description = "AWS region used to provision resources."
  type        = string
  default     = "us-east-1"
}

variable "db_instance_identifier" {
  description = "RDS instance identifier."
  type        = string
  default     = "classicmodels-db"
}

variable "db_name" {
  description = "Initial database name in the RDS instance."
  type        = string
  default     = "classicmodels"
}

variable "db_username" {
  description = "Master username for RDS."
  type        = string
  default     = "admin"
}

variable "db_password" {
  description = "Master password for RDS."
  type        = string
  sensitive   = true
}

variable "instance_class" {
  description = "RDS instance class."
  type        = string
  default     = "db.t3.micro"
}

variable "allowed_cidr" {
  description = "CIDR allowed to connect to MySQL port 3306."
  type        = string
  default     = "0.0.0.0/0"
}

variable "publicly_accessible" {
  description = "Whether the RDS instance should be publicly accessible."
  type        = bool
  default     = true
}
