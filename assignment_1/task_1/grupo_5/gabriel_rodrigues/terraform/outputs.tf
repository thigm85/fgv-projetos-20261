output "rds_endpoint" {
  description = "Host do MySQL."
  value       = aws_db_instance.this.address
}

output "rds_port" {
  description = "Porta MySQL."
  value       = aws_db_instance.this.port
}

output "rds_security_group_id" {
  description = "Security group deste RDS."
  value       = aws_security_group.rds_mysql.id
}

output "task2_s3_bucket" {
  description = "Bucket S3 onde o ETL grava Parquet e onde fica o script do Glue."
  value       = aws_s3_bucket.task2_curated.bucket
}

output "glue_connection_name" {
  description = "Nome da conexão Glue para o MySQL."
  value       = aws_glue_connection.rds_mysql.name
}

output "glue_job_name" {
  description = "Nome do job Glue de ETL."
  value       = aws_glue_job.etl_star_schema.name
}

output "glue_security_group_id" {
  description = "Security group usado pelo Glue para acessar o RDS."
  value       = aws_security_group.glue_etl.id
}
