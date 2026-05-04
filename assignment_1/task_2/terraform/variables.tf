##############################################################################
# Variáveis de configuração — Task 2: Pipeline ETL
#
# A maioria dos valores é detectada automaticamente da instância RDS
# criada na Task 1. Apenas a senha do RDS precisa ser fornecida.
##############################################################################

# ─── Região ─────────────────────────────────────────────────────────────────
variable "aws_region" {
  description = "Região AWS onde os recursos serão criados"
  type        = string
  default     = "us-east-1"
}

# ─── Projeto ────────────────────────────────────────────────────────────────
variable "project_name" {
  description = "Prefixo para nomear todos os recursos"
  type        = string
  default     = "classicmodels-etl"
}

# ─── RDS (valores da Task 1 — detectados automaticamente) ──────────────────
variable "rds_instance_id" {
  description = "Identifier da instância RDS criada na Task 1"
  type        = string
  default     = "classicmodels-db"
}

variable "rds_db_name" {
  description = "Nome do banco de dados no RDS"
  type        = string
  default     = "classicmodels"
}

variable "rds_password" {
  description = "Senha do RDS (mesma usada na Task 1)"
  type        = string
  sensitive   = true
  default     = "FGV_Projetos_2026!"
}
