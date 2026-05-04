output "rds_endpoint" {
  description = "Endpoint completo do banco de dados"
  value       = aws_db_instance.classicmodels_db.endpoint
}

output "rds_host" {
  description = "Host do banco de dados, sem porta"
  value       = aws_db_instance.classicmodels_db.address
}

output "rds_port" {
  description = "Porta do banco de dados"
  value       = aws_db_instance.classicmodels_db.port
}