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

variable "db_instance_id" {
  description = "ID da instancia RDS"
  type        = string
  default     = "classicmodels-db"
}

variable "db_name" {
  description = "Nome do banco de dados"
  type        = string
  default     = "classicmodels"
}

variable "db_username" {
  description = "Usuario do banco (passe por variavel de ambiente TF_VAR_db_username)"
  type        = string
  sensitive   = true
}

variable "db_password" {
  description = "Senha do banco (passe por variavel de ambiente TF_VAR_db_password)"
  type        = string
  sensitive   = true
}

variable "instance_class" {
  description = "Classe da instancia RDS (elegivel ao Free Tier)"
  type        = string
  default     = "db.t3.micro"
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
