output "etl_bucket_name" {
  value = aws_s3_bucket.etl.id
}

output "analytics_output_path" {
  value = local.output_path
}

output "glue_job_name" {
  value = aws_glue_job.classicmodels_incremental_etl.name
}

output "glue_connection_name" {
  value = aws_glue_connection.rds_mysql.name
}

output "glue_database_name" {
  value = aws_glue_catalog_database.analytics.name
}

output "fact_orders_location" {
  value = "${local.output_path}/fact_orders/"
}

output "eventbridge_schedule_name" {
  value = aws_scheduler_schedule.weekly_incremental_etl.name
}

output "eventbridge_schedule_arn" {
  value = aws_scheduler_schedule.weekly_incremental_etl.arn
}

output "glue_role_name" {
  value = local.glue_role_name
}
