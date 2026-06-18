output "s3_bucket_name" {
  description = "S3 bucket for transformed data"
  value       = aws_s3_bucket.data_lake.id
}

output "s3_output_path" {
  description = "S3 path where Parquet files are stored"
  value       = "s3://${aws_s3_bucket.data_lake.id}/analytics"
}

output "glue_job_name" {
  description = "Name of the Glue ETL job"
  value       = aws_glue_job.etl.name
}

output "glue_connection_name" {
  description = "Name of the Glue JDBC connection"
  value       = aws_glue_connection.mysql.name
}

output "glue_role_arn" {
  description = "ARN of the Glue IAM role"
  value       = data.aws_iam_role.lab_role.arn
}

output "glue_database_name" {
  description = "Glue Catalog database for Athena queries"
  value       = aws_glue_catalog_database.star_schema.name
}

output "athena_workgroup" {
  description = "Athena workgroup name"
  value       = aws_athena_workgroup.main.name
}

output "eventbridge_rule_name" {
  description = "EventBridge rule name for the scheduled ETL job"
  value       = aws_cloudwatch_event_rule.etl_schedule.name
}

output "eventbridge_rule_arn" {
  description = "EventBridge rule ARN for the scheduled ETL job"
  value       = aws_cloudwatch_event_rule.etl_schedule.arn
}

