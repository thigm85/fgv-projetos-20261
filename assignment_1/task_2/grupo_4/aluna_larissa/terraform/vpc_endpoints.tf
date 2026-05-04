data "aws_route_tables" "all" {
  vpc_id = var.vpc_id
}

data "aws_route_table" "main" {
  route_table_id = data.aws_route_tables.all.ids[0]
}

resource "aws_vpc_endpoint" "s3_gateway" {
  vpc_id            = var.vpc_id
  service_name      = "com.amazonaws.${var.aws_region}.s3"
  vpc_endpoint_type = "Gateway"

  route_table_ids = [
    data.aws_route_table.main.id
  ]

  tags = merge(local.tags, { Name = "${local.name_prefix}-s3-endpoint" })
}

