# ─── outputs.tf ───────────────────────────────────────────────────────────────
#
# Expõe os valores criados pelo módulo de duas formas:
#   1. Outputs Terraform — consultáveis via `terraform output`.
#   2. catalog_info.json — arquivo local gerado pelo resource local_file,
#      consumido diretamente por 1_setup_catalog.py, 2_validate_athena.py
#      e dashboard.ipynb sem necessitar de chamadas adicionais ao Terraform.
#
# O arquivo catalog_info.json está no .gitignore (não contém segredos, mas
# é gerado localmente e varia por ambiente).
# ──────────────────────────────────────────────────────────────────────────────

output "glue_database_name" {
  description = "Nome do Glue Catalog Database criado para o star schema."
  value       = aws_glue_catalog_database.analytics.name
}

output "crawler_name" {
  description = "Nome do Glue Crawler responsável por registrar as tabelas Parquet no catálogo."
  value       = aws_glue_crawler.star_schema.name
}

output "athena_output_path" {
  description = "Prefixo S3 onde o Athena armazena os resultados das queries (query results location)."
  value       = "s3://${var.s3_bucket_name}/athena-results/"
}

# Contrato entre Terraform e scripts Python: evita que os scripts executem
# `terraform output` ou hardcodem nomes de recursos.
resource "local_file" "catalog_info" {
  filename = "${path.module}/catalog_info.json"
  content = jsonencode({
    glue_database  = aws_glue_catalog_database.analytics.name
    s3_bucket_name = var.s3_bucket_name
    athena_output  = "s3://${var.s3_bucket_name}/athena-results/"
    crawler_name   = aws_glue_crawler.star_schema.name
  })
}
