# EventBridge semanal acionando o Glue Job incremental.
# Ajuste os nomes/ARNs para encaixar no Terraform do Assignment 1.

resource "aws_cloudwatch_event_rule" "classicmodels_sales_incremental_schedule" {
  name                = "classicmodels-sales-incremental-schedule"
  description         = "Executa o Glue Job incremental classicmodels_sales semanalmente"
  schedule_expression = var.incremental_schedule_expression
}

resource "aws_cloudwatch_event_target" "classicmodels_sales_incremental_target" {
  rule      = aws_cloudwatch_event_rule.classicmodels_sales_incremental_schedule.name
  target_id = "classicmodels-sales-incremental-glue-job"
  arn       = aws_glue_job.classicmodels_sales_incremental.arn
  role_arn  = aws_iam_role.eventbridge_glue_start_role.arn
}

resource "aws_iam_role" "eventbridge_glue_start_role" {
  name = "eventbridge-start-classicmodels-glue-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "events.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })
}

resource "aws_iam_role_policy" "eventbridge_start_glue_policy" {
  name = "eventbridge-start-classicmodels-glue-policy"
  role = aws_iam_role.eventbridge_glue_start_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["glue:StartJobRun"]
        Resource = aws_glue_job.classicmodels_sales_incremental.arn
      }
    ]
  })
}
