##############################################################################
# IAM Role para o AWS Glue
#
# No ambiente AWS Academy/Labs (voclabs), não temos permissão para criar
# novas IAM Roles (iam:CreateRole). Por isso, usaremos a LabRole já
# existente, que possui as permissões necessárias para o laboratório.
##############################################################################

data "aws_iam_role" "lab_role" {
  name = "LabRole"
}
