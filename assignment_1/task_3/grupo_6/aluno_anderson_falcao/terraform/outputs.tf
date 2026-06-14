output "rds_endpoint" {
  description = "Endpoint da instancia RDS provisionada"
  value       = aws_db_instance.main.address
}

output "rds_port" {
  description = "Porta do MySQL"
  value       = aws_db_instance.main.port
}

output "db_name" {
  description = "Nome do Banco de Dados"
  value       = aws_db_instance.main.db_name
}

output "s3_bucket_name" {
  description = "Nome do bucket S3 onde o Parquet será armazenado"
  value       = aws_s3_bucket.etl.bucket
}

output "athena_database_name" {
  description = "Nome do banco de dados do Athena"
  value       = aws_glue_catalog_database.analytics.name
}

output "athena_workgroup" {
  description = "Workgroup do Athena criado"
  value       = aws_athena_workgroup.analytics.name
}
