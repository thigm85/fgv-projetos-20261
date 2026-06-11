variable "incremental_schedule_expression" {
  description = "Cron do EventBridge para executar o Glue Job incremental"
  type        = string
  default     = "cron(0 12 ? * MON *)"
}

variable "glue_job_name" {
  description = "Nome do Glue Job incremental"
  type        = string
  default     = "classicmodels-sales-incremental"
}

variable "glue_role_arn" {
  description = "ARN da role usada pelo Glue Job. Em lab, normalmente é a LabRole."
  type        = string
}

variable "scripts_bucket" {
  description = "Bucket onde o script PySpark do Glue será salvo"
  type        = string
}

variable "analytics_bucket" {
  description = "Bucket do lake analítico"
  type        = string
}

variable "glue_database_name" {
  description = "Database do Glue Catalog usado pelo Athena"
  type        = string
  default     = "classicmodels_analytics"
}

variable "jdbc_url" {
  description = "URL JDBC do RDS MySQL: jdbc:mysql://host:3306/classicmodels"
  type        = string
  sensitive   = true
}

variable "jdbc_user" {
  description = "Usuário do banco classicmodels"
  type        = string
  sensitive   = true
}

variable "jdbc_password" {
  description = "Senha do banco classicmodels"
  type        = string
  sensitive   = true
}
