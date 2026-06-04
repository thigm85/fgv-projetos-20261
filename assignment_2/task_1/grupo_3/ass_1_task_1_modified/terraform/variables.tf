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

  validation {
    condition     = length(var.db_password) >= 12
    error_message = "db_password must have at least 12 characters."
  }
}

variable "instance_class" {
  description = "RDS instance class."
  type        = string
  default     = "db.t3.micro"
}

variable "allowed_cidr" {
  description = "Optional CIDR allowed to connect to MySQL port 3306. Use only a trusted /32 in lab mode."
  type        = string
  default     = null

  validation {
    condition     = var.allowed_cidr == null || (var.allowed_cidr != "0.0.0.0/0" && can(cidrhost(var.allowed_cidr, 0)))
    error_message = "allowed_cidr must be null or a valid restricted CIDR. Never use 0.0.0.0/0."
  }
}

variable "publicly_accessible" {
  description = "Whether the RDS instance should be publicly accessible. Keep false unless running the local lab workflow."
  type        = bool
  default     = false
}

variable "deletion_protection" {
  description = "Enable deletion protection for the RDS instance."
  type        = bool
  default     = true
}
