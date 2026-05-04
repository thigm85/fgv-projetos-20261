##############################################################################
# AWS Glue Connection — JDBC para MySQL no RDS
#
# Usa os dados detectados automaticamente da instância RDS da Task 1
# via data sources em data.tf. Nenhuma configuração manual necessária.
##############################################################################

resource "aws_glue_connection" "mysql_rds" {
  name            = "${var.project_name}-mysql-connection"
  connection_type = "JDBC"

  connection_properties = {
    JDBC_CONNECTION_URL = "jdbc:mysql://${local.rds_endpoint}:${local.rds_port}/${var.rds_db_name}"
    USERNAME            = local.rds_username
    PASSWORD            = var.rds_password
  }

  physical_connection_requirements {
    availability_zone      = local.availability_zone
    security_group_id_list = [local.security_group_id]
    subnet_id              = local.subnet_id
  }
}
