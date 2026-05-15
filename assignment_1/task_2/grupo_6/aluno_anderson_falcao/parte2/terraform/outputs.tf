output "s3_bucket_name" {
  description = "Nome do bucket S3 criado para o ETL"
  value       = aws_s3_bucket.etl.bucket
}

output "s3_bucket_arn" {
  description = "ARN do bucket S3"
  value       = aws_s3_bucket.etl.arn
}

output "glue_job_name" {
  description = "Nome do Glue Job (use para disparar via CLI ou 3_validate_etl.py)"
  value       = aws_glue_job.etl.name
}

output "glue_connection_name" {
  description = "Nome da Glue Connection JDBC"
  value       = aws_glue_connection.mysql.name
}

output "glue_script_s3_path" {
  description = "Caminho S3 do script PySpark do Glue"
  value       = "s3://${aws_s3_bucket.etl.bucket}/scripts/2_glue_etl_job.py"
}

output "s3_data_prefix" {
  description = "Prefixo S3 onde os dados Parquet serão gravados"
  value       = "s3://${aws_s3_bucket.etl.bucket}/data/"
}

output "aws_cli_trigger_command" {
  description = "Comando AWS CLI para disparar o Glue Job"
  value       = "aws glue start-job-run --job-name ${aws_glue_job.etl.name} --region ${var.region}"
}
