# ─── main.tf ──────────────────────────────────────────────────────────────────
#
# Módulo raiz da Task 3 — Catálogo Glue para o star schema do classicmodels.
#
# Responsabilidade: declara os providers e versões mínimas exigidas.
# Os recursos (Glue Database, Crawler, catalog_info.json) estão em
# glue_catalog.tf e outputs.tf.
#
# Provider "local" é necessário para gerar catalog_info.json via
# local_file (outputs.tf), permitindo que os scripts Python e o notebook
# leiam as saídas do Terraform sem executar `terraform output`.
# ──────────────────────────────────────────────────────────────────────────────

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    local = {
      source  = "hashicorp/local"
      version = "~> 2.0"
    }
  }
}

provider "aws" {
  region     = var.aws_region
  access_key = var.aws_access_key_id
  secret_key = var.aws_secret_access_key
  token      = var.aws_session_token
}
