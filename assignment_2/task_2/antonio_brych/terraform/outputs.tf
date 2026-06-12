output "etl_bucket_name" {
  value       = aws_s3_bucket.etl.id
  description = "S3 bucket used for the ETL pipeline."
}

output "analytics_root" {
  value       = local.analytics_root
  description = "Root S3 prefix for all analytics tables."
}

output "glue_job_name" {
  value       = aws_glue_job.classicmodels_incremental_etl.name
  description = "Name of the Glue job to trigger manually or via EventBridge."
}

output "glue_connection_name" {
  value       = aws_glue_connection.rds_mysql.name
  description = "Glue JDBC connection name."
}

output "glue_database_name" {
  value       = aws_glue_catalog_database.analytics.name
  description = "Glue Catalog database visible in Athena."
}

output "fact_orders_location" {
  value       = "${local.analytics_root}/fact_orders/"
  description = "S3 location of the fact_orders table."
}

output "eventbridge_schedule_name" {
  value       = aws_scheduler_schedule.weekly_etl.name
  description = "EventBridge Scheduler name."
}

output "eventbridge_schedule_arn" {
  value       = aws_scheduler_schedule.weekly_etl.arn
  description = "EventBridge Scheduler ARN."
}

output "glue_role_name" {
  value       = local.glue_role_name
  description = "IAM role name used by the Glue job."
}
