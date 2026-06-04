# ─── glue_catalog.tf ──────────────────────────────────────────────────────────
#
# Recursos Glue responsáveis por registrar o star schema no Glue Catalog,
# tornando as tabelas Parquet do S3 consultáveis via Amazon Athena.
#
# Fluxo de dados:
#   Task 2 (Glue ETL) → Parquet em S3 (s3://<bucket>/data/<tabela>/)
#                     ↓
#   aws_glue_crawler  → lê pastas e infere schema
#                     ↓
#   aws_glue_catalog_database → registra tabelas (dim_*/fact_*)
#                     ↓
#   Amazon Athena     → consulta SQL sobre as tabelas do catálogo
# ──────────────────────────────────────────────────────────────────────────────

# ─── Glue Catalog Database ────────────────────────────────────────────────────
# Namespace lógico que agrupa as tabelas do star schema no Glue Catalog.
# O nome é exposto como saída em catalog_info.json para uso no notebook.

resource "aws_glue_catalog_database" "analytics" {
  name = var.glue_database_name
}

# ─── IAM Role (LabRole pré-existente do AWS Academy) ─────────────────────────
# O AWS Academy bloqueia criação de IAM Roles via API; por isso reutilizamos
# a LabRole pré-existente, que já possui as permissões necessárias para
# Glue ler do S3 e escrever logs no CloudWatch.

data "aws_iam_role" "lab_role" {
  name = "LabRole"
}

# ─── Glue Crawler ─────────────────────────────────────────────────────────────
# Rastreia o prefixo s3://<bucket>/data/ e registra uma tabela por subpasta:
#   data/dim_customers/  → dim_customers
#   data/dim_products/   → dim_products
#   data/dim_dates/      → dim_dates
#   data/dim_countries/  → dim_countries
#   data/fact_orders/    → fact_orders
#
# MergeNewColumns: novas colunas adicionadas por re-execuções do ETL da Task 2
# são incorporadas ao schema existente sem recriar a tabela inteira.

resource "aws_glue_crawler" "star_schema" {
  name          = "classicmodels-star-schema-crawler"
  role          = data.aws_iam_role.lab_role.arn
  database_name = aws_glue_catalog_database.analytics.name

  s3_target {
    path = "s3://${var.s3_bucket_name}/data/"
  }

  configuration = jsonencode({
    Version = 1.0
    CrawlerOutput = {
      Tables = { AddOrUpdateBehavior = "MergeNewColumns" }
    }
  })

  tags = { Name = "classicmodels-star-schema-crawler" }
}
