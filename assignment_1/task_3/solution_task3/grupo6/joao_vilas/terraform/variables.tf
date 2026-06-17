variable "aws_region" {
  description = "Regiao AWS usada no laboratorio"
  type        = string
  default     = "us-east-1"
}

variable "project_prefix" {
  description = "Prefixo dos recursos da Task 3"
  type        = string
  default     = "joao-vilas-task3"

  validation {
    condition     = can(regex("^[a-z0-9-]+$", var.project_prefix))
    error_message = "Use apenas letras minusculas, numeros e hifen."
  }
}

variable "owner_tag" {
  description = "Tag de owner aplicada a todos os recursos"
  type        = string
  default     = "grupo6-joao-vilas"
}

variable "db_identifier" {
  description = "Identificador da instancia RDS"
  type        = string
  default     = "classicmodels-rds-task3"
}

variable "db_username" {
  description = "Usuario administrador do MySQL"
  type        = string
  default     = "admin"
}

variable "db_name" {
  description = "Nome do banco carregado pela Task 1"
  type        = string
  default     = "classicmodels"
}

variable "allowed_mysql_cidr" {
  description = "IP publico autorizado a acessar o MySQL no formato x.x.x.x/32"
  type        = string

  validation {
    condition = (
      can(cidrhost(var.allowed_mysql_cidr, 0)) &&
      can(regex("/32$", var.allowed_mysql_cidr)) &&
      var.allowed_mysql_cidr != "0.0.0.0/0" &&
      var.allowed_mysql_cidr != "0.0.0.0/32"
    )
    error_message = "Use seu IP publico atual no formato x.x.x.x/32. Nao use 0.0.0.0/0."
  }
}

variable "glue_database_name" {
  description = "Nome do database no Glue Data Catalog usado pelo Athena"
  type        = string
  default     = "joao_vilas_task3_classicmodels"

  validation {
    condition     = can(regex("^[a-z0-9_]+$", var.glue_database_name))
    error_message = "Nome do database Glue deve usar letras minusculas, numeros e underscore."
  }
}

variable "lab_role_name" {
  description = "Nome da IAM Role pre-existente no AWS Learner Lab. Esta stack NUNCA cria roles; ela apenas referencia uma existente (geralmente 'LabRole')."
  type        = string
  default     = "LabRole"
}

variable "enable_sagemaker_notebook" {
  description = "Provisionar SageMaker Notebook Instance para rodar o dashboard na AWS"
  type        = bool
  default     = true
}

variable "sagemaker_instance_type" {
  description = "Tipo de instancia para o SageMaker Notebook (compativel com Learner Lab)"
  type        = string
  default     = "ml.t3.medium"
}

variable "sagemaker_volume_size_gb" {
  description = "Tamanho do volume EBS do notebook em GB"
  type        = number
  default     = 10
}

variable "rds_allocated_storage_gb" {
  description = "Storage RDS em GB"
  type        = number
  default     = 20
}

variable "rds_instance_class" {
  description = "Classe da instancia RDS"
  type        = string
  default     = "db.t3.micro"
}
