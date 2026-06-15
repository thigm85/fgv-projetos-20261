output "aws_region" {
  description = "Regiao AWS configurada"
  value       = var.aws_region
}

output "rds_endpoint" {
  description = "Endpoint completo do banco de dados"
  value       = aws_db_instance.classicmodels_db.endpoint
}

output "rds_host" {
  description = "Host do banco de dados, sem porta"
  value       = aws_db_instance.classicmodels_db.address
}

output "rds_port" {
  description = "Porta do banco de dados"
  value       = aws_db_instance.classicmodels_db.port
}

output "db_secret_id" {
  description = "Nome (name) do segredo no Secrets Manager com as credenciais do RDS"
  value       = aws_secretsmanager_secret.db_credentials.name
}

output "db_secret_arn" {
  description = "ARN do segredo do RDS"
  value       = aws_secretsmanager_secret.db_credentials.arn
}

output "etl_bucket_name" {
  description = "Bucket S3 com o star schema em Parquet"
  value       = aws_s3_bucket.etl_bucket.bucket
}

output "etl_output_s3_path" {
  description = "Prefixo S3 onde as tabelas Parquet sao gravadas"
  value       = "s3://${aws_s3_bucket.etl_bucket.bucket}/${local.output_prefix}"
}

output "glue_connection_name" {
  description = "Nome da conexao JDBC do Glue com o RDS"
  value       = aws_glue_connection.classicmodels_mysql.name
}

output "glue_job_name" {
  description = "Nome do Glue Job de ETL"
  value       = aws_glue_job.classicmodels_etl.name
}

output "glue_database" {
  description = "Database no Glue Data Catalog usado pelo Athena"
  value       = aws_glue_catalog_database.classicmodels.name
}

output "glue_tables" {
  description = "Tabelas registradas no Glue Data Catalog"
  value       = [for t in aws_glue_catalog_table.tables : t.name]
}

output "athena_workgroup" {
  description = "Workgroup do Athena"
  value       = aws_athena_workgroup.task3.name
}

output "athena_results_bucket" {
  description = "Bucket S3 com os resultados das queries do Athena"
  value       = aws_s3_bucket.athena_results.bucket
}

output "athena_output_s3" {
  description = "Local S3 onde o Athena salva os resultados"
  value       = "s3://${aws_s3_bucket.athena_results.bucket}/results/"
}

output "sagemaker_notebook_name" {
  description = "Nome do notebook do SageMaker (vazio quando enable_sagemaker_notebook = false)"
  value       = var.enable_sagemaker_notebook ? aws_sagemaker_notebook_instance.task3[0].name : ""
}

output "sagemaker_notebook_url" {
  description = "URL do JupyterLab no SageMaker (vazio quando desabilitado)"
  value = var.enable_sagemaker_notebook ? format(
    "https://%s.notebook.%s.sagemaker.aws/lab",
    aws_sagemaker_notebook_instance.task3[0].name,
    var.aws_region,
  ) : ""
}

output "notebook_s3_uri" {
  description = "Local do notebook publicado no S3"
  value       = "s3://${aws_s3_bucket.etl_bucket.bucket}/${local.notebook_bucket_key}"
}

output "athena_named_queries" {
  description = "IDs das named queries criadas no Athena workgroup"
  value = {
    dim_products_preview = aws_athena_named_query.dim_products_preview.id
    sales_by_country     = aws_athena_named_query.sales_by_country.id
    sales_detail         = aws_athena_named_query.sales_detail.id
  }
}
