resource "aws_glue_connection" "mysql" {
  count             = length(aws_security_group.glue) > 0 ? 1 : 0
  name              = "${local.name}-mysql"
  connection_type = "JDBC"

  connection_properties = {
    JDBC_CONNECTION_URL = trimspace(var.glue_mysql_jdbc_suffix) == "" ? "jdbc:mysql://${local.rds_endpoint}:${local.rds_mysql_port}/${var.rds_database}" : "jdbc:mysql://${local.rds_endpoint}:${local.rds_mysql_port}/${var.rds_database}${var.glue_mysql_jdbc_suffix}"
    USERNAME            = var.glue_db_username
    PASSWORD            = var.glue_db_password
  }

  physical_connection_requirements {
    availability_zone      = data.aws_subnet.glue_subnet[0].availability_zone
    subnet_id              = data.aws_subnet.glue_subnet[0].id
    security_group_id_list = [aws_security_group.glue[0].id]
  }

  tags = {
    Project = local.name
  }

  depends_on = [
    aws_security_group_rule.rds_mysql_from_glue,
    aws_security_group_rule.glue_self_all_tcp_ingress,
  ]

  lifecycle {
    precondition {
      condition     = trimspace(var.rds_instance_identifier) != ""
      error_message = "Defina rds_instance_identifier para usar o modo automático."
    }
  }
}
