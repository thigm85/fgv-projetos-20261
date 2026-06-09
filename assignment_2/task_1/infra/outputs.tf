output "rds_endpoint" {
  value = aws_db_instance.classicmodels.address
}

output "rds_port" {
  value = aws_db_instance.classicmodels.port
}

output "rds_security_group_id" {
  value = aws_security_group.rds.id
}

# Gera pipeline_info.json diretamente em scripts/ para os scripts Python lerem.
resource "local_file" "pipeline_info" {
  filename = "${path.module}/../scripts/pipeline_info.json"
  content = jsonencode({
    rds_endpoint   = aws_db_instance.classicmodels.address
    rds_port       = aws_db_instance.classicmodels.port
    rds_db_name    = "classicmodels"
    rds_admin_user = var.rds_admin_user
  })
}
