output "rds_endpoint" {
  value = aws_db_instance.mysql.endpoint
}

output "rds_port" {
  value = aws_db_instance.mysql.port
}

output "vpc_id" {
  value = aws_vpc.main.id
}

output "db_instance_identifier" {
  value = aws_db_instance.mysql.id
}

output "allowed_cidr" {
  value = var.allowed_cidr
}

output "etl_bucket_name" {
  value = aws_s3_bucket.etl.id
}

output "glue_job_name" {
  value = aws_glue_job.classicmodels_etl.name
}

output "glue_connection_name" {
  value = aws_glue_connection.rds_mysql.name
}
