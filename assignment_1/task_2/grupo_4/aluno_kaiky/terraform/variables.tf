variable "aws_region" {
  type        = string
  description = "AWS region for all resources."
  default     = "us-east-1"
}

variable "project_name" {
  type        = string
  description = "Prefix for resource names."
  default     = "classicmodels-etl"
}

# --- RDS / rede (modo automático) ---
# Informe o `rds_instance_identifier` e o Terraform descobre endpoint, porta,
# subnets do DB subnet group e SGs do RDS; cria SG do Glue e abre MySQL.

variable "rds_instance_identifier" {
  type        = string
  description = "Identificador da instância RDS (ex.: my-mysql-1)."
}

variable "rds_database" {
  type        = string
  description = "Catalog name on MySQL (classicmodels)."
  default     = "classicmodels"
}

variable "glue_db_username" {
  type        = string
  description = "MySQL user for Glue (prefer a read-only account)."
  sensitive   = true
}

variable "glue_db_password" {
  type        = string
  description = "MySQL password for Glue. Pass via TF_VAR_glue_db_password or a .tfvars not committed to git."
  sensitive   = true
}

variable "glue_job_role_arn" {
  type        = string
  description = "ARN de role IAM existente para o Glue Job. Se informado, o Terraform nao tenta criar role/policy."
  default     = ""
}

variable "create_s3_vpc_endpoint" {
  type        = bool
  description = "Se true, cria endpoint Gateway de S3 na VPC do Glue e associa nas route tables das subnets do Glue."
  default     = true
}

variable "glue_mysql_jdbc_suffix" {
  type        = string
  description = "Sufixo da URL JDBC (inclua o ?). Inclui allowPublicKeyRetrieval para MySQL 8 (caching_sha2_password). Vazio = sem query string."
  default     = "?useSSL=false&allowPublicKeyRetrieval=true&serverTimezone=UTC&connectTimeout=120000&socketTimeout=120000"
}

variable "glue_worker_type" {
  type        = string
  description = "Glue worker type."
  default     = "G.1X"
}

variable "glue_number_of_workers" {
  type        = number
  description = "Number of Glue workers."
  default     = 2
}

variable "glue_max_concurrent_runs" {
  type        = number
  description = "Limite de runs simultaneos deste job. Em labs, >1 evita ConcurrentRunsExceeded enquanto um run ainda esta STOPPING/retentando."
  default     = 3
}

variable "glue_version" {
  type        = string
  default     = "4.0"
}

variable "python_version" {
  type        = string
  default     = "3"
}
