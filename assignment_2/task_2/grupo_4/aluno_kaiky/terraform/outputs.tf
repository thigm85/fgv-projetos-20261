output "s3_bucket_name" {
  value       = aws_s3_bucket.etl.bucket
  description = "Bucket where Parquet outputs and Glue script live."
}

output "glue_connection_name" {
  value       = aws_glue_connection.mysql.name
  description = "Glue connection to MySQL."
}

output "glue_job_name" {
  value       = aws_glue_job.etl.name
  description = "Glue job name to run."
}

output "glue_role_arn_in_use" {
  value       = data.aws_iam_role.glue.arn
  description = "Existing IAM role ARN used by the Glue job."
}

output "glue_database_name" {
  value       = aws_glue_catalog_database.star.name
  description = "Glue/Athena database for star-schema tables (use as GLUE_DATABASE in Task 3 notebook)."
}

output "rds_endpoint" {
  value       = local.rds_endpoint
  description = "RDS hostname resolved from Task 1 instance (data.aws_db_instance.source)."
}

output "analytics_prefix" {
  value       = local.analytics_prefix
  description = "S3 prefix for star-schema Parquet outputs."
}

output "eventbridge_rule_name" {
  value       = var.eventbridge_enabled ? aws_glue_trigger.etl_schedule[0].name : null
  description = "Glue scheduled trigger name (cron). EventBridge PutTargets cannot target Glue job ARNs directly."
}

output "eventbridge_schedule" {
  value       = var.glue_schedule_cron
  description = "Cron expression for scheduled Glue runs (UTC)."
}

