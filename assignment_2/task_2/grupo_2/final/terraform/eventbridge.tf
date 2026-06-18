# EventBridge — agenda semanal do Glue job incremental.
#
# IAM: role dedicada para EventBridge com permissão mínima (glue:StartJobRun).
# No AWS Academy com LabRole fixa, troque aws_iam_role por data "aws_iam_role"
# e aponte existing_role_arn para LabRole (documentado no README).

data "aws_caller_identity" "current" {}

resource "aws_iam_role" "eventbridge_glue" {
  name = "classicmodels-eventbridge-glue-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "events.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "eventbridge_glue_inline" {
  name = "AllowStartGlueJob"
  role = aws_iam_role.eventbridge_glue.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "glue:StartJobRun"
      Resource = aws_glue_job.etl.arn
    }]
  })
}

resource "aws_cloudwatch_event_rule" "weekly_etl" {
  name                = "classicmodels-etl-weekly"
  description         = "Disparo semanal do Glue Job incremental classicmodels"
  schedule_expression = "cron(0 12 ? * MON *)"
  state               = "ENABLED"
}

resource "aws_cloudwatch_event_target" "glue_job" {
  rule      = aws_cloudwatch_event_rule.weekly_etl.name
  target_id = "classicmodels-incremental-glue-job"
  arn       = "arn:aws:glue:us-east-1:${data.aws_caller_identity.current.account_id}:job/${aws_glue_job.etl.name}"
  role_arn  = aws_iam_role.eventbridge_glue.arn

  input = jsonencode({
    Arguments = {
      "--pipeline_name" = "classicmodels_sales"
    }
  })
}

# Fallback: Glue Trigger agendado — usado em labs onde EventBridge rejeita
# Glue Job ARN como target direto ("Provided Arn is not in correct format").
resource "aws_glue_trigger" "weekly_etl_fallback" {
  name     = "classicmodels-etl-weekly-trigger"
  type     = "SCHEDULED"
  schedule = "cron(0 12 ? * MON *)"
  enabled  = false # habilitar só se aws_cloudwatch_event_target falhar no lab

  actions {
    job_name = aws_glue_job.etl.name
  }
}
