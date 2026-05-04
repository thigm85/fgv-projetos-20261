##############################################################################
# Security Group — Regra adicional para o Glue acessar o RDS
#
# O Glue Job roda dentro da VPC (cria ENIs na subnet). Para ele conectar
# ao RDS na porta 3306, o SG do RDS precisa permitir tráfego de si mesmo
# (self-referencing), pois o Glue usa o mesmo SG configurado na conexão.
##############################################################################

resource "aws_security_group_rule" "glue_self_reference" {
  type                     = "ingress"
  from_port                = 0
  to_port                  = 65535
  protocol                 = "tcp"
  security_group_id        = local.security_group_id
  source_security_group_id = local.security_group_id
  description              = "Glue ENIs - self-referencing para ETL job"
}
