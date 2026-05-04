output "rds_endpoint" {
  description = "RDS instance endpoint"
  value       = data.aws_db_instance.classicmodels_rds.endpoint
}

output "rds_port" {
  description = "RDS instance port"
  value       = data.aws_db_instance.classicmodels_rds.port
}

output "rds_username" {
  description = "RDS master username"
  value       = var.username
}

output "rds_password" {
  description = "RDS master password"
  value       = var.password
  sensitive   = true
}

output "rds_database" {
  description = "RDS database name"
  value       = data.aws_db_instance.classicmodels_rds.db_name
}

output "s3_bucket_name" {
  description = "S3 bucket name for data lake"
  value       = aws_s3_bucket.data_lake.bucket
}

output "s3_bucket_arn" {
  description = "S3 bucket ARN"
  value       = aws_s3_bucket.data_lake.arn
}

output "glue_job_name" {
  description = "Glue job name"
  value       = aws_glue_job.etl_job.name
}

output "glue_database_name" {
  description = "Glue catalog database name"
  value       = aws_glue_catalog_database.classicmodels.name
}