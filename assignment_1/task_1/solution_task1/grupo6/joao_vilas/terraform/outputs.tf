output "rds_endpoint" {
  description = "O endpoint de conexao do banco de dados"
  value       = aws_db_instance.classicmodels_db.endpoint
}