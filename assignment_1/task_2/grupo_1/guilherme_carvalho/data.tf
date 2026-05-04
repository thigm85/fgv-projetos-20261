data "aws_caller_identity" "current" {}

data "aws_db_instance" "source" {
  db_instance_identifier = var.rds_instance_id
}

data "aws_db_subnet_group" "rds" {
  name = data.aws_db_instance.source.db_subnet_group
}

data "aws_subnets" "rds_az" {
  filter {
    name = "vpc-id"
    values = [data.aws_db_subnet_group.rds.vpc_id]
  }

  filter {
    name = "availability-zone"
    values = [data.aws_db_instance.source.availability_zone]
  }
}

locals {
  rds_endpoint = "${data.aws_db_instance.source.address}:${data.aws_db_instance.source.port}"
  rds_security_group_id = tolist(data.aws_db_instance.source.vpc_security_groups)[0]
  rds_subnet_id = tolist(data.aws_subnets.rds_az.ids)[0]
  rds_availability_zone = data.aws_db_instance.source.availability_zone
}
