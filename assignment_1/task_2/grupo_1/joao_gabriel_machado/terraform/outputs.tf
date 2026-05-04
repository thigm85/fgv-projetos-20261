output "rds_endpoint" {
  description = "Endpoint de conexao do banco de dados"
  value       = aws_db_instance.sales_analytics.address
}

output "security_group_id" {
  description = "ID do Security Group criado"
  value       = aws_security_group.rds_sg.id
}