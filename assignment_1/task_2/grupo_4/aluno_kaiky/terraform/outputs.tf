output "s3_bucket_name" {
  description = "Bucket for Parquet output and Glue scripts."
  value       = aws_s3_bucket.data_lake.id
}

output "s3_star_schema_prefix" {
  description = "S3 URI prefix where fact/dim Parquet folders are written."
  value       = "s3://${aws_s3_bucket.data_lake.bucket}/${local.data_prefix}"
}

output "glue_job_name" {
  description = "Name of the Glue ETL job (vazio se a rede/RDS não permitiu criar a connection)."
  value       = try(aws_glue_job.classicmodels_star_schema[0].name, "")
}

output "glue_connection_name" {
  description = "Glue JDBC connection to RDS MySQL."
  value       = try(aws_glue_connection.mysql[0].name, "")
}

output "glue_security_group_id" {
  description = "Security group criado para ENIs do Glue (ingress no RDS referencia este SG)."
  value       = try(aws_security_group.glue[0].id, "")
}

output "glue_iam_role_arn" {
  description = "IAM role assumed by the Glue job."
  value       = try(aws_iam_role.glue_etl[0].arn, var.glue_job_role_arn)
}
