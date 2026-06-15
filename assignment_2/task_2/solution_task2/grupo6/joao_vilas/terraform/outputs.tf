output "aws_region" {
  description = "Região AWS configurada"
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
  description = "Nome do secret no Secrets Manager com as credenciais do RDS"
  value       = aws_secretsmanager_secret.db_credentials.name
}

output "etl_bucket_name" {
  description = "Bucket S3 com o star schema em Parquet"
  value       = aws_s3_bucket.etl_bucket.bucket
}

output "analytics_prefix" {
  description = "Prefixo S3 onde o star schema é gravado"
  value       = local.analytics_prefix
}

output "fact_orders_s3_location" {
  description = "Caminho S3 base de fact_orders (particionado por order_year/order_month)"
  value       = local.fact_s3_location
}

output "glue_connection_name" {
  description = "Nome da conexão JDBC do Glue com o RDS"
  value       = aws_glue_connection.classicmodels_mysql.name
}

output "glue_job_name" {
  description = "Nome do Glue Job de ETL incremental"
  value       = aws_glue_job.classicmodels_incremental_etl.name
}

output "glue_database" {
  description = "Database no Glue Data Catalog usado pelo Athena"
  value       = aws_glue_catalog_database.classicmodels.name
}

output "athena_workgroup" {
  description = "Workgroup do Athena"
  value       = aws_athena_workgroup.a2t2.name
}

output "eventbridge_rule_name" {
  description = "Nome da regra cron do EventBridge"
  value       = aws_cloudwatch_event_rule.etl_schedule.name
}

output "scheduler_lambda_name" {
  description = "Lambda que dispara o Glue Job (target do EventBridge)"
  value       = aws_lambda_function.start_glue_job.function_name
}
