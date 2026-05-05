variable "aws_region" {
  type        = string
  description = "Região AWS (ex.: us-east-1)."
  default     = "us-east-1"
}

variable "db_identifier" {
  type        = string
  description = "Identificador da instância RDS."
  default     = "classicmodels-db"
}

variable "db_subnet_group_name" {
  type        = string
  description = "DB subnet group existente."
  default     = "default"
}

variable "db_username" {
  type        = string
  description = "Usuário master do MySQL."
  default     = "admin"
}

variable "db_password" {
  type        = string
  description = "Senha do master."
  sensitive   = true
}

variable "project_name" {
  type        = string
  description = "Prefixo amigável para nomear recursos da Task 2."
  default     = "fgv-grupo5-gabriel"
}

variable "glue_role_arn" {
  type        = string
  description = "ARN de uma IAM Role EXISTENTE que o AWS Glue possa assumir (no Learner Lab geralmente uma role como LabRole)."
}

variable "glue_subnet_id" {
  type        = string
  description = "Subnet ID para o Glue Connection (defina explicitamente no Learner Lab para evitar escolha errada)."
  default     = null
}

# Quem pode conectar na porta 3306 (além dos security groups abaixo).
variable "allowed_cidr_blocks" {
  type        = list(string)
  description = "CIDRs com acesso MySQL. Para laboratório costuma-se IP/32; 0.0.0.0/0 abre para qualquer lugar."
  default     = []
}

# Security groups externos autorizados a conectar no MySQL deste RDS.
variable "allowed_security_group_ids" {
  type        = list(string)
  description = "IDs de security groups (ex.: de um bastion ou EC2) que podem acessar a porta 3306."
  default     = []
}
