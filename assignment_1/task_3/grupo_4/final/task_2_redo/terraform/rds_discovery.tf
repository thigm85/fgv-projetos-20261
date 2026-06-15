# Discover RDS endpoint and network from the Task 1 instance (identifier matches 01_provision_rds.py).
data "aws_db_instance" "source" {
  db_instance_identifier = var.rds_db_instance_identifier
}

data "aws_db_subnet_group" "rds" {
  name = data.aws_db_instance.source.db_subnet_group
}

locals {
  rds_endpoint = data.aws_db_instance.source.address
  # Some API responses return 0 for db_instance_port; fall back to 3306.
  rds_port = (
    data.aws_db_instance.source.port > 0 ? data.aws_db_instance.source.port :
    (data.aws_db_instance.source.db_instance_port > 0 ? data.aws_db_instance.source.db_instance_port : var.rds_port)
  )
  vpc_id = data.aws_db_subnet_group.rds.vpc_id

  glue_subnet_ids = sort(tolist(data.aws_db_subnet_group.rds.subnet_ids))
  rds_az          = data.aws_db_instance.source.availability_zone
}

data "aws_subnet" "db_subnet_group_subnet" {
  for_each = toset(local.glue_subnet_ids)
  id       = each.key
}

locals {
  glue_subnet_ids_same_az = sort([
    for sid in local.glue_subnet_ids : sid
    if data.aws_subnet.db_subnet_group_subnet[sid].availability_zone == local.rds_az
  ])
  glue_connection_subnet_id = (
    length(local.glue_subnet_ids_same_az) > 0 ? local.glue_subnet_ids_same_az[0] :
    (length(local.glue_subnet_ids) > 0 ? local.glue_subnet_ids[0] : null)
  )

  # First RDS security group unless overridden in tfvars
  rds_security_group_ids = data.aws_db_instance.source.vpc_security_groups
  glue_sg_id_resolved = coalesce(
    var.glue_sg_id,
    length(local.rds_security_group_ids) > 0 ? local.rds_security_group_ids[0] : null,
  )
}

data "aws_subnet" "glue" {
  id = local.glue_connection_subnet_id
}
