output "rds_endpoint" {
  description = "Endpoint da instância de RDS recuperada."
  value       = data.aws_db_instance.classicmodels.address
}

output "glue_job_name" {
  description = "Nome do AWS Glue Job criado."
  value       = aws_glue_job.classicmodels_incremental.name
}

output "glue_connection_name" {
  description = "Nome do AWS Glue Connection criado."
  value       = aws_glue_connection.classicmodels_incremental.name
}

output "analytics_bucket_name" {
  description = "Nome do S3 Bucket criado para o data lake."
  value       = aws_s3_bucket.analytics.bucket
}

output "glue_catalog_database_name" {
  description = "Nome do banco de dados no catálogo Glue."
  value       = aws_glue_catalog_database.analytics.name
}

output "eventbridge_rule_arn" {
  description = "ARN do agendamento CloudWatch Event (EventBridge) criado."
  value       = aws_cloudwatch_event_rule.glue_cron.arn
}
