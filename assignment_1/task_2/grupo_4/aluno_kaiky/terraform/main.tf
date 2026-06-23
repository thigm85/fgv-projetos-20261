locals {
  name          = var.project_name
  script_prefix = "glue/assets"
  data_prefix   = "warehouse/star"
}

data "aws_db_instance" "source" {
  db_instance_identifier = var.rds_instance_identifier
}

data "aws_db_subnet_group" "rds" {
  # AWS provider: attribute is `db_subnet_group` (not `db_subnet_group_name`).
  name = data.aws_db_instance.source.db_subnet_group
}

locals {
  # Prefer `db_instance_port` for RDS MySQL; `port` is mainly for Aurora endpoints.
  rds_mysql_port = coalesce(
    data.aws_db_instance.source.db_instance_port,
    data.aws_db_instance.source.port,
  )
  rds_endpoint = data.aws_db_instance.source.address
  # `subnet_ids` is a set; convert to sorted list for stable indexing.
  glue_subnet_ids = sort(tolist(data.aws_db_subnet_group.rds.subnet_ids))
}

data "aws_subnet" "db_subnet_group_subnet" {
  for_each = toset(local.glue_subnet_ids)
  id       = each.key
}

locals {
  # Glue JDBC: prefer subnet na mesma AZ do RDS (evita falhas de link em alguns labs).
  rds_az = data.aws_db_instance.source.availability_zone
  glue_subnet_ids_same_az = sort([
    for sid in local.glue_subnet_ids : sid
    if data.aws_subnet.db_subnet_group_subnet[sid].availability_zone == local.rds_az
  ])
  glue_connection_subnet_id = (
    length(local.glue_subnet_ids_same_az) > 0 ? local.glue_subnet_ids_same_az[0] :
    (length(local.glue_subnet_ids) > 0 ? local.glue_subnet_ids[0] : null)
  )

  # AWS provider: `vpc_security_groups` is a list of security group id strings
  # (the old flat attribute `vpc_security_group_ids` was removed).
  rds_security_group_ids = data.aws_db_instance.source.vpc_security_groups
}
