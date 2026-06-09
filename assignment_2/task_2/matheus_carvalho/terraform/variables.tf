variable "aws_region" {
  description = "Região AWS utilizada para provisionar os recursos."
  type        = string
  default     = "us-east-1"
}

variable "project_prefix" {
  description = "Prefixo utilizado no nome de todos os recursos para evitar colisões."
  type        = string
  default     = "g2-matheus-task2"
}

variable "db_identifier" {
  description = "Identificador da instância de RDS MySQL que já está ativa no console."
  type        = string
  default     = "classicmodels-db"
}

variable "db_name" {
  description = "Nome do banco de dados na instância RDS."
  type        = string
  default     = "classicmodels"
}

variable "bucket_name" {
  description = "Nome do S3 Bucket para o data lake. Se deixado vazio, será auto-gerado com base na conta."
  type        = string
  default     = ""
}

variable "glue_job_name" {
  description = "Nome do AWS Glue Job incremental."
  type        = string
  default     = "classicmodels-incremental-etl-job"
}

variable "glue_connection_name" {
  description = "Nome da AWS Glue Connection para acessar o RDS."
  type        = string
  default     = "classicmodels-incremental-rds-conn"
}

variable "existing_glue_role_name" {
  description = "Nome da role IAM existente para o Glue Job (geralmente LabRole no AWS Academy)."
  type        = string
  default     = "LabRole"
}

variable "glue_script_key" {
  description = "Localização do script do Glue Job dentro do bucket S3."
  type        = string
  default     = "glue/etl_job.py"
}

variable "cron_expression" {
  description = "Expressão Cron do EventBridge para o agendamento do Glue Job."
  type        = string
  default     = "cron(0 12 ? * MON *)" # Toda segunda-feira às 12:00 UTC
}
