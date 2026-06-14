variable "region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Prefixo para nomeacao de todos os recursos"
  type        = string
  default     = "classicmodels"
}

variable "rds_host" {
  description = "Endpoint da instancia RDS (do rds_credentials.json)"
  type        = string
}

variable "rds_port" {
  description = "Porta MySQL"
  type        = number
  default     = 3306
}

variable "db_name" {
  description = "Nome do banco de dados"
  type        = string
  default     = "classicmodels"
}

variable "db_username" {
  description = "Usuario do banco (use TF_VAR_db_username para nao expor no arquivo)"
  type        = string
  sensitive   = true
}

variable "db_password" {
  description = "Senha do banco (use TF_VAR_db_password para nao expor no arquivo)"
  type        = string
  sensitive   = true
}

variable "glue_worker_type" {
  description = "Tipo de worker do Glue (G.1X e o menor disponivel no Academy)"
  type        = string
  default     = "G.1X"
}

variable "glue_number_of_workers" {
  description = "Numero de workers do Glue (minimo 2)"
  type        = number
  default     = 2
}

variable "glue_timeout_minutes" {
  description = "Timeout do Job do Glue em minutos"
  type        = number
  default     = 60
}
