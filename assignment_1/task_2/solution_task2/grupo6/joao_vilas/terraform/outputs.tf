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

output "etl_bucket_name" {
  description = "Bucket S3 usado pela Task 2"
  value       = aws_s3_bucket.etl_bucket.bucket
}

output "etl_output_s3_path" {
  description = "Prefixo S3 onde as tabelas Parquet serão gravadas"
  value       = "s3://${aws_s3_bucket.etl_bucket.bucket}/${local.output_prefix}"
}

output "glue_connection_name" {
  description = "Nome da conexão JDBC do Glue com o RDS MySQL"
  value       = aws_glue_connection.classicmodels_mysql.name
}

output "glue_job_name" {
  description = "Nome do Glue Job ETL"
  value       = aws_glue_job.classicmodels_etl.name
}

output "glue_role_arn" {
  description = "ARN da role usada pelo Glue"
  value       = local.glue_role_arn
}