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

variable "db_password" {
  description = "Senha do banco de dados RDS"
  type        = string
  sensitive   = true
}

variable "allowed_mysql_cidr" {
  description = "IP público autorizado a acessar o MySQL, no formato x.x.x.x/32"
  type        = string

  validation {
    condition = (
      can(cidrhost(var.allowed_mysql_cidr, 0)) &&
      can(regex("/32$", var.allowed_mysql_cidr)) &&
      var.allowed_mysql_cidr != "0.0.0.0/0" &&
      var.allowed_mysql_cidr != "0.0.0.0/32"
    )

    error_message = "Use seu IP público atual no formato x.x.x.x/32. Não use 0.0.0.0/0 nem 0.0.0.0/32."
  }
}

variable "db_name" {
  description = "Nome do banco carregado na Task 1"
  type        = string
  default     = "classicmodels"
}

variable "project_prefix" {
  description = "Prefixo dos recursos da Task 2"
  type        = string
  default     = "joao-vilas-task2"

  validation {
    condition     = can(regex("^[a-z0-9-]+$", var.project_prefix))
    error_message = "Use apenas letras minúsculas, números e hífen."
  }
}

variable "use_existing_lab_role" {
  description = "Usar a role LabRole existente do AWS Learner Lab em vez de criar uma IAM Role nova"
  type        = bool
  default     = true
}

variable "existing_glue_role_name" {
  description = "Nome da IAM Role existente no Learner Lab"
  type        = string
  default     = "LabRole"
}