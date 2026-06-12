output "rds_endpoint" {
  value       = aws_db_instance.mysql.address
  description = "Endpoint of the RDS MySQL instance"
}

output "rds_port" {
  value       = aws_db_instance.mysql.port
  description = "RDS MySQL port"
}

output "s3_bucket_name" {
  value       = aws_s3_bucket.analytics.id
  description = "Name of the analytics S3 bucket"
}

output "glue_job_name" {
  value       = aws_glue_job.incremental_etl.name
  description = "Name of the incremental Glue job"
}

output "glue_database_name" {
  value       = aws_glue_catalog_database.analytics.name
  description = "Glue Catalog database name"
}

output "eventbridge_rule_name" {
  value       = aws_cloudwatch_event_rule.weekly_etl.name
  description = "EventBridge rule name"
}

output "glue_workflow_name" {
  value       = aws_glue_workflow.etl.name
  description = "Name of the Glue workflow triggered by EventBridge"
}
