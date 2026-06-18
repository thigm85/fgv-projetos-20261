data "aws_vpc" "rds" {
  id = data.aws_db_subnet_group.rds.vpc_id
}

data "aws_route_tables" "rds_vpc" {
  vpc_id = data.aws_vpc.rds.id
}

resource "aws_vpc_endpoint" "s3" {
  vpc_id = data.aws_vpc.rds.id
  service_name = "com.amazonaws.${var.aws_region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids = data.aws_route_tables.rds_vpc.ids
}
