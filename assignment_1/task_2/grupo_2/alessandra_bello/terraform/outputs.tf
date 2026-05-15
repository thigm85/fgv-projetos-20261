output "rds_endpoint" {
  description = "RDS endpoint used by the source database."
  value       = aws_db_instance.classicmodels.address
}

output "glue_job_name" {
  description = "AWS Glue job name."
  value       = aws_glue_job.classicmodels.name
}

output "glue_connection_name" {
  description = "AWS Glue connection name."
  value       = aws_glue_connection.classicmodels.name
}

output "analytics_bucket_name" {
  description = "S3 bucket used for script storage and parquet outputs."
  value       = aws_s3_bucket.analytics.bucket
}

output "rds_security_group_id" {
  description = "Security group attached to the RDS instance."
  value       = aws_security_group.rds.id
}

output "glue_security_group_id" {
  description = "Security group attached to Glue networking."
  value       = aws_security_group.glue.id
}
