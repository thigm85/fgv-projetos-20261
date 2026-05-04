##############################################################################
# S3 VPC Endpoint
#
# O AWS Glue, ao rodar dentro de uma VPC para se conectar ao RDS via JDBC,
# precisa de uma rota para o S3 (para ler o script e gravar o output).
# Em ambientes sem NAT Gateway, usamos um VPC Endpoint (Gateway) para o S3.
##############################################################################

# Obtém a tabela de roteamento principal da VPC
data "aws_route_table" "main_rt" {
  vpc_id = local.vpc_id
}

# Cria o VPC Endpoint (tipo Gateway) para o S3
resource "aws_vpc_endpoint" "s3" {
  vpc_id       = local.vpc_id
  service_name = "com.amazonaws.${var.aws_region}.s3"
  
  route_table_ids = [
    data.aws_route_table.main_rt.id
  ]
}
