resource "random_password" "db_password" {
  length           = 24
  special          = true
  override_special = "!@#%^*-_=+"

  keepers = {
    db_identifier = var.db_identifier
  }
}

resource "aws_secretsmanager_secret" "db_credentials" {
  name        = "${var.project_prefix}/rds/classicmodels"
  description = "Credenciais do RDS MySQL classicmodels usadas por Glue, scripts locais e notebook."

  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "db_credentials" {
  secret_id = aws_secretsmanager_secret.db_credentials.id

  secret_string = jsonencode({
    engine   = "mysql"
    username = var.db_username
    password = random_password.db_password.result
    host     = aws_db_instance.classicmodels_db.address
    port     = aws_db_instance.classicmodels_db.port
    dbname   = var.db_name
  })
}
