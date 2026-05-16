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

