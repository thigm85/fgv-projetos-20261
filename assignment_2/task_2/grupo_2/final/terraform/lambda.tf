# ==========================================================================
# Lambda gateway — valida pedidos simulados antes de inserir no RDS.
#
# Uso pelo simulate:
#   - simulate --via-lambda chama boto3.client("lambda").invoke(...)
#   - Lambda valida payload e insere em transação no RDS.
#   - Sem flag, simulate insere direto no RDS (gate desativado).
#
# Empacotamento:
#   - pymysql vai em um Lambda Layer (reusável, mantém o pacote do handler
#     leve — pymysql é puro Python, sem partes compiladas).
#   - O handler vai num ZIP só com order_gateway.py.
# ==========================================================================

# ---------------------------------------------------------------------------
# Layer: pymysql.
#   pip install em layer_build/python/ → AWS Lambda monta esse path no
#   PYTHONPATH automaticamente quando a layer é anexada à função.
# ---------------------------------------------------------------------------
resource "null_resource" "lambda_layer_build" {
  triggers = {
    requirements = filemd5("${path.module}/../lambda/requirements.txt")
  }

  provisioner "local-exec" {
    command = <<-EOT
      set -e
      cd ${path.module}/../lambda
      rm -rf layer_build
      mkdir -p layer_build/python
      pip install --quiet -r requirements.txt -t layer_build/python/
    EOT
  }
}

data "archive_file" "lambda_layer_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../lambda/layer_build"
  output_path = "${path.module}/lambda_layer_mysql.zip"

  depends_on = [null_resource.lambda_layer_build]
}

resource "aws_lambda_layer_version" "mysql_connector" {
  layer_name          = "classicmodels-mysql-connector"
  description         = "pymysql para Lambdas do lab"
  filename            = data.archive_file.lambda_layer_zip.output_path
  source_code_hash    = data.archive_file.lambda_layer_zip.output_base64sha256
  compatible_runtimes = ["python3.11"]
}

# ---------------------------------------------------------------------------
# Handler: ZIP só com o código (sem dependências).
# ---------------------------------------------------------------------------
data "archive_file" "lambda_handler_zip" {
  type        = "zip"
  source_file = "${path.module}/../lambda/order_gateway.py"
  output_path = "${path.module}/lambda_order_gateway.zip"
}

# ---------------------------------------------------------------------------
# Security group da Lambda + regras de rede.
# ---------------------------------------------------------------------------
resource "aws_security_group" "lambda" {
  name        = "lab-lambda-sg"
  description = "Lambda order gateway networking"
  vpc_id      = data.aws_vpc.default.id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# RDS aceita ingress da Lambda na porta 3306.
resource "aws_security_group_rule" "rds_from_lambda" {
  type                     = "ingress"
  from_port                = 3306
  to_port                  = 3306
  protocol                 = "tcp"
  security_group_id        = aws_security_group.rds.id
  source_security_group_id = aws_security_group.lambda.id
  description              = "Lambda gateway to RDS MySQL"
}

# Lambda fala HTTPS com VPC endpoint do Secrets Manager (SG do endpoint = SG do Glue).
resource "aws_security_group_rule" "secretsmanager_from_lambda" {
  type                     = "ingress"
  from_port                = 443
  to_port                  = 443
  protocol                 = "tcp"
  security_group_id        = aws_security_group.glue.id
  source_security_group_id = aws_security_group.lambda.id
  description              = "Lambda gateway to Secrets Manager VPC endpoint"
}

# ---------------------------------------------------------------------------
# Lambda function.
# ---------------------------------------------------------------------------
resource "aws_lambda_function" "order_gateway" {
  function_name    = "classicmodels-order-gateway"
  role             = local.glue_role_arn # reusa LabRole
  runtime          = "python3.11"
  handler          = "order_gateway.lambda_handler"
  filename         = data.archive_file.lambda_handler_zip.output_path
  source_code_hash = data.archive_file.lambda_handler_zip.output_base64sha256
  timeout          = 30
  memory_size      = 256

  layers = [aws_lambda_layer_version.mysql_connector.arn]

  vpc_config {
    subnet_ids         = data.aws_subnets.rds_az.ids
    security_group_ids = [aws_security_group.lambda.id]
  }

  environment {
    variables = {
      SECRET_ARN = aws_secretsmanager_secret.db_secret.arn
      DB_NAME    = "classicmodels"
    }
  }

  depends_on = [aws_db_instance.mysql]
}

output "lambda_order_gateway_name" {
  value       = aws_lambda_function.order_gateway.function_name
  description = "Nome da Lambda gateway — usar no simulate --via-lambda"
}
