output "glue_job_name" {
  value = aws_glue_job.etl_job.name
}

output "s3_bucket_name" {
  value = aws_s3_bucket.etl_bucket.id
}

output "glue_crawler_name" {
  value = aws_glue_crawler.gold_crawler.name
}

output "athena_workgroup" {
  value = aws_athena_workgroup.main.name
}

output "glue_database_name" {
  value = aws_glue_catalog_database.classicmodels_gold.name
}
