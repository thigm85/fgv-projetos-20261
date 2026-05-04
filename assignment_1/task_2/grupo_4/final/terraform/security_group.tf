resource "aws_security_group" "glue_connection" {
  name        = "${local.name_prefix}-glue-conn-sg"
  description = "Glue Connection SG (self-ingress all ports, egress all)"
  vpc_id      = var.vpc_id
  tags        = local.tags
}

# Glue requirement (in some labs): at least one SG must allow all inbound ports.
# Restricting source to itself limits the exposure to ENIs within this SG.
resource "aws_security_group_rule" "glue_self_ingress_all" {
  type              = "ingress"
  security_group_id = aws_security_group.glue_connection.id

  from_port = 0
  to_port   = 0
  protocol  = "-1"

  self = true
}

resource "aws_security_group_rule" "glue_egress_all" {
  type              = "egress"
  security_group_id = aws_security_group.glue_connection.id

  from_port   = 0
  to_port     = 0
  protocol    = "-1"
  cidr_blocks = ["0.0.0.0/0"]
}

locals {
  # Always include the "self-ingress all ports" SG to satisfy Glue validation.
  # If user provides an additional SG id, include it too.
  glue_connection_sg_ids = var.glue_sg_id == null ? [aws_security_group.glue_connection.id] : [
    aws_security_group.glue_connection.id,
    var.glue_sg_id
  ]
}

