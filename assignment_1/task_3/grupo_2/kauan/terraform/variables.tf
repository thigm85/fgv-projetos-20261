variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "db_host" {
  type = string
}

variable "db_port" {
  type = string
}

variable "db_name" {
  type = string
}

variable "db_user" {
  type = string
}

variable "db_password" {
  type      = string
  sensitive = true
}

variable "vpc_id" {
  type = string
}

variable "subnet_id" {
  type = string
}

variable "rds_sg_id" {
  type = string
}
