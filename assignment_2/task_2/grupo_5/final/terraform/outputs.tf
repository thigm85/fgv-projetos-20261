output "s3_bucket_name" {
  description = "Bucket com scripts e saídas Parquet particionadas"
  value       = aws_s3_bucket.etl_bucket.id
}

output "glue_job_name" {
  description = "Nome do job Glue incremental"
  value       = aws_glue_job.etl_job.name
}

output "glue_connection_name" {
  description = "Nome da conexão JDBC Glue"
  value       = aws_glue_connection.mysql_connection.name
}

output "glue_database_name" {
  description = "Database Glue Catalog para Athena"
  value       = aws_glue_catalog_database.analytics.name
}

output "fact_orders_s3_path" {
  description = "Prefixo S3 de fact_orders particionado"
  value       = "s3://${aws_s3_bucket.etl_bucket.id}/analytics/fact_orders/"
}

output "eventbridge_rule_name" {
  description = "Regra EventBridge que agenda o job"
  value       = aws_cloudwatch_event_rule.glue_schedule.name
}

output "glue_workflow_name" {
  description = "Workflow Glue acionado pelo EventBridge"
  value       = aws_glue_workflow.etl.name
}

output "eventbridge_role_arn" {
  description = "LabRole usada pelo EventBridge para invocar o workflow Glue"
  value       = var.glue_role_arn
}
