variable "aws_region" {
  description = "Região da AWS onde os recursos serão criados"
  type        = string
  default     = "us-east-1"
}

variable "db_name" {
  description = "Nome do banco de dados inicial"
  type        = string
  default     = "classicmodels"
}

variable "db_username" {
  description = "Usuário administrador do RDS"
  type        = string
  default     = "admin"
}

variable "db_password" {
  description = "Senha do administrador (definida via env ou tfvars)"
  type        = string
  sensitive   = true
}