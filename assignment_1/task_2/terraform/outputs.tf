##############################################################################
# Outputs — valores úteis após terraform apply
##############################################################################

output "s3_output_bucket" {
  description = "Nome do bucket S3 com os Parquets (star schema)"
  value       = aws_s3_bucket.etl_output.id
}

output "s3_assets_bucket" {
  description = "Nome do bucket S3 com scripts e temp do Glue"
  value       = aws_s3_bucket.glue_assets.id
}

output "glue_job_name" {
  description = "Nome do Glue Job para iniciar via CLI"
  value       = aws_glue_job.etl_classicmodels.name
}

output "glue_connection_name" {
  description = "Nome da conexão Glue JDBC"
  value       = aws_glue_connection.mysql_rds.name
}

output "glue_role_arn" {
  description = "ARN da IAM Role do Glue"
  value       = data.aws_iam_role.lab_role.arn
}

# ─── Valores detectados da Task 1 (útil para debug) ────────────────────────
output "detected_rds_endpoint" {
  description = "Endpoint do RDS detectado automaticamente"
  value       = local.rds_endpoint
}

output "detected_vpc_id" {
  description = "VPC ID detectada"
  value       = local.vpc_id
}

output "detected_subnet_id" {
  description = "Subnet ID usada pelo Glue"
  value       = local.subnet_id
}

output "detected_security_group_id" {
  description = "Security Group ID do RDS"
  value       = local.security_group_id
}
