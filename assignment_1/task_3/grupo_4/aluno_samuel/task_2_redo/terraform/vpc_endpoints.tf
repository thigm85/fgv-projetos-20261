# Main route table for the VPC (avoids empty ids[0] when vpc_id is wrong or filtered)
data "aws_route_table" "main" {
  vpc_id = local.vpc_id

  filter {
    name   = "association.main"
    values = ["true"]
  }
}

resource "aws_vpc_endpoint" "s3_gateway" {
  vpc_id            = local.vpc_id
  service_name      = "com.amazonaws.${var.aws_region}.s3"
  vpc_endpoint_type = "Gateway"

  route_table_ids = [
    data.aws_route_table.main.id
  ]

  tags = merge(local.tags, { Name = "${local.name_prefix}-s3-endpoint" })
}

