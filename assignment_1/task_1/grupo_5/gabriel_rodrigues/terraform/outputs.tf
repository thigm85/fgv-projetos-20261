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
