variable "aws_region" {
  description = "Região AWS usada no laboratório"
  type        = string
  default     = "us-east-1"
}

variable "project_prefix" {
  description = "Prefixo dos recursos da Task 2"
  type        = string
  default     = "joao-vilas-a2t2"

  validation {
    condition     = can(regex("^[a-z0-9-]+$", var.project_prefix))
    error_message = "Use apenas letras minúsculas, números e hífen."
  }
}

variable "owner_tag" {
  description = "Tag de owner aplicada a todos os recursos"
  type        = string
  default     = "grupo6-joao-vilas"
}

variable "db_identifier" {
  description = "Identificador da instância RDS"
  type        = string
  default     = "classicmodels-rds-a2t2"
}

variable "db_username" {
  description = "Usuário administrador do MySQL"
  type        = string
  default     = "admin"
}

variable "db_name" {
  description = "Nome do banco classicmodels"
  type        = string
  default     = "classicmodels"
}

variable "pipeline_name" {
  description = "Chave do pipeline na tabela etl_watermark"
  type        = string
  default     = "classicmodels_sales"
}

variable "allowed_mysql_cidr" {
  description = "IP público autorizado a acessar o MySQL no formato x.x.x.x/32"
  type        = string

  validation {
    condition = (
      can(cidrhost(var.allowed_mysql_cidr, 0)) &&
      can(regex("/32$", var.allowed_mysql_cidr)) &&
      var.allowed_mysql_cidr != "0.0.0.0/0" &&
      var.allowed_mysql_cidr != "0.0.0.0/32"
    )
    error_message = "Use seu IP público atual no formato x.x.x.x/32. Não use 0.0.0.0/0."
  }
}

variable "glue_database_name" {
  description = "Database no Glue Data Catalog usado pelo Athena"
  type        = string
  default     = "joao_vilas_a2t2_classicmodels"

  validation {
    condition     = can(regex("^[a-z0-9_]+$", var.glue_database_name))
    error_message = "Use letras minúsculas, números e underscore."
  }
}

variable "lab_role_name" {
  description = "IAM Role pré-existente do AWS Learner Lab. Esta stack NUNCA cria roles; apenas referencia a existente (geralmente 'LabRole')."
  type        = string
  default     = "LabRole"
}

variable "rds_allocated_storage_gb" {
  description = "Storage RDS em GB"
  type        = number
  default     = 20
}

variable "rds_instance_class" {
  description = "Classe da instância RDS"
  type        = string
  default     = "db.t3.micro"
}

variable "schedule_expression" {
  description = "Cron do EventBridge para disparar o ETL (UTC). Default: semanal, segunda, meio-dia."
  type        = string
  default     = "cron(0 12 ? * MON *)"
}

variable "partition_year_range" {
  description = "Faixa de anos (min,max) para partition projection de order_year no Athena"
  type        = string
  default     = "2000,2035"
}
