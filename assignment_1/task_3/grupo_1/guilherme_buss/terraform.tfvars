# Task 3 Terraform Configuration

aws_region            = "us-east-1"
aws_profile           = "default"
project_name          = "classic-models"

# IMPORTANTE: Substitua pelo nome do database da Task 2
# Este deve ser o mesmo database onde o Glue job da Task 2 criou as tabelas
glue_database_name    = "classicmodels"

# Deixe vazio para deixar o Terraform gerar automaticamente
# Ou especifique um nome de bucket S3 que já existe
athena_output_bucket  = ""

# Prefixo/caminho dentro do bucket para resultados do Athena
athena_output_prefix  = "athena-results/"

tags = {
  Project     = "ClassicModels"
  Environment = "Development"
  Task        = "Task3-Analytics"
  CreatedBy   = "Terraform"
}
