variable "db_password" {
  description = "A senha do banco de dados RDS para a conexão JDBC do Glue"
  type        = string
  sensitive   = true
}

# Para inciar o terraform corretamente, é necessário rodar no powershell:
# $env:TF_VAR_db_password ="SENHA_AQUI"