variable "aws_region" {
  description = "Regiao da AWS"
  type        = string
  default     = "us-east-1"
}

variable "db_identifier" {
  description = "Nome da instancia RDS"
  type        = string
}

variable "db_user" {
  description = "Usuario admin do banco"
  type        = string
}

variable "db_password" {
  description = "Senha do administrador do RDS"
  type        = string
  sensitive   = true
}

variable "my_ip" {
  description = "Seu IP publico local com mascara"
  type        = string
}