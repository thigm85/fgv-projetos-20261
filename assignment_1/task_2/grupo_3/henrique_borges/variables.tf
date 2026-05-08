variable "aws_region" {
  default = "us-east-1"
}

variable "aws_access_key_id" {
  sensitive = true
}

variable "aws_secret_access_key" {
  sensitive = true
}

variable "aws_session_token" {
  sensitive = true
}

# --- RDS ---

variable "rds_instance_id" {
  description = "Identificador único da instância RDS (sem espaços ou caracteres especiais)"
  default     = "classicmodels-grupo3"
}

variable "rds_admin_user" {
  default = "admin"
}

variable "rds_admin_password" {
  description = "Senha do usuário admin do RDS (mínimo 8 caracteres)"
  sensitive   = true
}

# --- Glue / S3 ---

variable "s3_bucket_name" {
  description = "Nome globalmente único para o bucket S3 do data lake"
}
