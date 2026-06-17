output "rds_endpoint" {
  description = "Endereço de conexão do banco"
  value       = aws_db_instance.mysql_source.endpoint
}

output "rds_database_name" {
  description = "Nome do banco de dados"
  value       = aws_db_instance.mysql_source.db_name
}

output "rds_username" {
  description = "Usuário mestre"
  value       = aws_db_instance.mysql_source.username
}

output "rds_port" {
  description = "Porta de conexão"
  value       = aws_db_instance.mysql_source.port
}