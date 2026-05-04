output "s3_bucket_name" {
  description = "S3 bucket for transformed data"
  value = aws_s3_bucket.data_lake.id
}

output "s3_output_path" {
  description = "S3 path where Parquet files are stored"
  value = "s3://${aws_s3_bucket.data_lake.id}/output"
}

output "glue_job_name" {
  description = "Name of the Glue ETL job"
  value = aws_glue_job.etl.name
}

output "glue_connection_name" {
  description = "Name of the Glue JDBC connection"
  value = aws_glue_connection.mysql.name
}

output "glue_role_arn" {
  description = "ARN of the Glue IAM role"
  value = data.aws_iam_role.lab_role.arn
}
