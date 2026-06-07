output "rds_endpoint" {
  value       = aws_db_instance.mysql.address
  description = "Endpoint do RDS MySQL"
}

output "rds_port" {
  value       = aws_db_instance.mysql.port
  description = "Porta do RDS"
}

output "s3_bucket_name" {
  value       = aws_s3_bucket.analytics.id
  description = "Nome do bucket S3 analytics"
}

output "glue_job_name" {
  value       = aws_glue_job.incremental_etl.name
  description = "Nome do Glue Job incremental"
}

output "glue_database_name" {
  value       = aws_glue_catalog_database.analytics.name
  description = "Database no Glue Catalog"
}

output "eventbridge_rule_name" {
  value       = aws_cloudwatch_event_rule.weekly_etl.name
  description = "Nome da regra EventBridge"
}

output "glue_workflow_name" {
  value       = aws_glue_workflow.etl.name
  description = "Nome do Glue Workflow acionado pelo EventBridge"
}
