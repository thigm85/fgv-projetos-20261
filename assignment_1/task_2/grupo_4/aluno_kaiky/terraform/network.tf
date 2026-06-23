# Security group dedicado ao Glue + ingress nos SGs do RDS (sem console).

data "aws_subnet" "glue_subnet" {
  count = local.glue_connection_subnet_id != null ? 1 : 0
  id    = local.glue_connection_subnet_id
}

data "aws_route_tables" "glue_vpc" {
  count = (var.create_s3_vpc_endpoint && length(data.aws_subnet.glue_subnet) > 0) ? 1 : 0

  filter {
    name   = "vpc-id"
    values = [data.aws_subnet.glue_subnet[0].vpc_id]
  }
}

resource "aws_security_group" "glue" {
  count  = length(data.aws_subnet.glue_subnet) > 0 ? 1 : 0
  vpc_id = data.aws_subnet.glue_subnet[0].vpc_id

  name_prefix = "${local.name}-glue-"
  description = "ENIs do AWS Glue (${local.name}) para JDBC ao RDS"

  egress {
    description = "Glue precisa de egress (S3, APIs AWS, MySQL ao RDS)"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Project = local.name
    Name    = "${local.name}-glue"
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_vpc_endpoint" "s3_gateway" {
  count             = (var.create_s3_vpc_endpoint && length(data.aws_subnet.glue_subnet) > 0) ? 1 : 0
  vpc_id            = data.aws_subnet.glue_subnet[0].vpc_id
  vpc_endpoint_type = "Gateway"
  service_name      = "com.amazonaws.${var.aws_region}.s3"
  route_table_ids   = data.aws_route_tables.glue_vpc[0].ids

  tags = {
    Project = local.name
    Name    = "${local.name}-s3-endpoint"
  }
}

resource "aws_security_group_rule" "glue_self_all_tcp_ingress" {
  count = length(aws_security_group.glue) > 0 ? 1 : 0

  type              = "ingress"
  from_port         = 0
  to_port           = 65535
  protocol          = "tcp"
  security_group_id = aws_security_group.glue[0].id
  self              = true
  description       = "AWS Glue requer ingress TCP interno no proprio SG"
}

resource "aws_security_group_rule" "rds_mysql_from_glue" {
  for_each = (
    length(aws_security_group.glue) > 0 &&
    length(local.rds_security_group_ids) > 0
  ) ? toset(local.rds_security_group_ids) : toset([])

  type                     = "ingress"
  from_port                = local.rds_mysql_port
  to_port                  = local.rds_mysql_port
  protocol                 = "tcp"
  source_security_group_id = aws_security_group.glue[0].id
  security_group_id        = each.value
  description              = "MySQL do Glue (${local.name})"
}
