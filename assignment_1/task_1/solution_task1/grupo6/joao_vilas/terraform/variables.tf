variable "db_password" {
  description = "Senha do banco de dados RDS"
  type        = string
  sensitive   = true
}
variable "aws_region" {
  description = "Região AWS usada no laboratório"
  type        = string
  default     = "us-east-1"
}

variable "db_identifier" {
  description = "Identificador da instância RDS"
  type        = string
  default     = "classicmodels-rds-lab"
}

variable "db_username" {
  description = "Usuário administrador do MySQL"
  type        = string
  default     = "admin"
}

variable "allowed_mysql_cidr" {
  description = "IP público autorizado a acessar o MySQL, no formato x.x.x.x/32"
  type        = string

  validation {
    condition     = can(cidrhost(var.allowed_mysql_cidr, 0)) && var.allowed_mysql_cidr != "0.0.0.0/0"
    error_message = "Use um CIDR específico, preferencialmente seu IP público com /32. Não use 0.0.0.0/0."
  }
}

variable "db_password" {
  description = "Senha do banco de dados RDS"
  type        = string
  sensitive   = true
}