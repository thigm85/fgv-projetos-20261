output "s3_bucket_name" {
  description = "Nome do bucket S3 do Data Lake"
  value       = aws_s3_bucket.datalake.bucket
}

output "s3_bucket_arn" {
  description = "ARN do bucket S3"
  value       = aws_s3_bucket.datalake.arn
}

output "glue_job_name" {
  description = "Nome do Glue Job"
  value       = aws_glue_job.etl_job.name
}

output "glue_connection_name" {
  description = "Nome da Glue Connection"
  value       = aws_glue_connection.rds_connection.name
}

output "data_output_path" {
  description = "Caminho S3 onde os dados Parquet serão gravados"
  value       = "s3://${aws_s3_bucket.datalake.bucket}/data/"
}
