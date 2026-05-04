resource "local_file" "env_file" {
  content  = <<-EOT
    DB_IDENTIFIER=${var.db_identifier}
    DB_USER=${var.db_user}
    DB_PASSWORD=${var.db_password}
    SECURITY_GROUP_ID=${aws_security_group.rds_sg.id}
    DB_HOST=${aws_db_instance.sales_analytics.address}
  EOT
  filename = "${path.module}/../sql/.env"
}

# Executa o script Python após a criação do banco e do arquivo .env
resource "null_resource" "setup_database" {
  triggers = {
    rds_instance_id = aws_db_instance.sales_analytics.id
  }

  # depends_on garante a ordem de execução: RDS -> .env -> Script
  depends_on = [
    aws_db_instance.sales_analytics,
    local_file.env_file
  ]

  provisioner "local-exec" {
    working_dir = "${path.module}/../sql"
    command     = "python add_data_db.py"
  }
}