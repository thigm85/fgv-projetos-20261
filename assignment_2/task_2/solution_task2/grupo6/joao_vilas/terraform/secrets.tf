resource "random_password" "db_password" {
  length           = 24
  special          = true
  override_special = "!@#%^*-_=+"

  keepers = {
    db_identifier = var.db_identifier
  }
}

# Credenciais JDBC em Secrets Manager (recomendação 3.1.3 do brief). O Glue Job lê o
# secret em runtime para atualizar o watermark; nenhuma senha é commitada no repositório.
resource "aws_secretsmanager_secret" "db_credentials" {
  name                    = "${var.project_prefix}/rds/classicmodels"
  description             = "Credenciais do RDS MySQL classicmodels (Glue, scripts e watermark)."
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
