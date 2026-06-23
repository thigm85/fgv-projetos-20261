output "s3_bucket_name" {
  description = "Bucket containing ETL scripts and curated parquet outputs"
  value       = aws_s3_bucket.etl_bucket.id
}

output "glue_job_name" {
  description = "Glue job name to run ETL"
  value       = aws_glue_job.etl_job.name
}

output "glue_connection_name" {
  description = "Glue JDBC connection name"
  value       = aws_glue_connection.mysql_connection.name
}

output "glue_catalog_database_name" {
  description = "Glue Catalog database for Athena"
  value       = aws_glue_catalog_database.analytics_db.name
}

output "glue_crawler_name" {
  description = "Glue crawler for curated datasets"
  value       = aws_glue_crawler.curated_crawler.name
}
