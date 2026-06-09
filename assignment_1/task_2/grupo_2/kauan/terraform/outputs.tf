output "glue_job_name" {
  value = aws_glue_job.etl_job.name
}

output "s3_bucket_name" {
  value = aws_s3_bucket.etl_bucket.id
}
