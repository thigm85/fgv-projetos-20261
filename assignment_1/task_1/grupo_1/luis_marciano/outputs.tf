output "rds_endpoint" {
  description = "RDS instance endpoint"
  value       = aws_db_instance.classicmodels_rds.endpoint
}

output "rds_port" {
  description = "RDS instance port"
  value       = aws_db_instance.classicmodels_rds.port
}

output "rds_username" {
  description = "RDS master username"
  value       = aws_db_instance.classicmodels_rds.username
}

output "rds_password" {
  description = "RDS master password"
  value       = aws_db_instance.classicmodels_rds.password
  sensitive   = true
}

output "rds_database" {
  description = "RDS database name"
  value       = aws_db_instance.classicmodels_rds.db_name
}