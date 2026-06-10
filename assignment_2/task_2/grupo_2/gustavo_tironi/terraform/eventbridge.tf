# EventBridge Scheduler — agenda execuções automáticas do Glue job incremental.
# IAM: usa local.glue_role_arn (LabRole, já definido em main.tf); criar uma
# role dedicada não é permitido no AWS Academy.

resource "aws_scheduler_schedule" "weekly_etl" {
  name       = "classicmodels-etl-weekly"
  group_name = "default"

  flexible_time_window {
    mode = "OFF"
  }

  schedule_expression = "cron(0 12 ? * MON *)"

  target {
    arn      = "arn:aws:scheduler:::aws-sdk:glue:startJobRun"
    role_arn = local.glue_role_arn

    input = jsonencode({
      JobName = aws_glue_job.etl.name
    })
  }
}
