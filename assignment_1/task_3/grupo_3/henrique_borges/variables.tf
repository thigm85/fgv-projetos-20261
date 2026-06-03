# ─── variables.tf ─────────────────────────────────────────────────────────────
#
# Declaração de todas as variáveis de entrada do módulo.
#
# Valores sensíveis (credenciais AWS) são fornecidos via terraform.tfvars,
# que é gerado em tempo de execução por 1_setup_catalog.py a partir do .env
# e está listado no .gitignore — nunca deve ser commitado.
# ──────────────────────────────────────────────────────────────────────────────

variable "aws_region" {
  description = "Região AWS onde os recursos Glue/Athena serão criados."
  default     = "us-east-1"
}

variable "aws_access_key_id" {
  description = "AWS Access Key ID (credencial temporária do AWS Academy Lab)."
  sensitive   = true
}

variable "aws_secret_access_key" {
  description = "AWS Secret Access Key (credencial temporária do AWS Academy Lab)."
  sensitive   = true
}

variable "aws_session_token" {
  description = "AWS Session Token exigido pelas credenciais temporárias STS do Lab."
  sensitive   = true
}

variable "s3_bucket_name" {
  description = "Nome do bucket S3 do data lake criado na Task 2 (ex: classicmodels-datalake-grupo3-henrique). O crawler aponta para s3://<bucket>/data/."
}

variable "glue_database_name" {
  description = "Nome do Glue Catalog Database a criar para o star schema analítico."
  default     = "classicmodels_analytics"
}
