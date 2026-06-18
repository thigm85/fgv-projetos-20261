# ---------------------------------------------------------------------------
# EventBridge Trigger for the Glue ETL job
# ---------------------------------------------------------------------------
# Fires weekly on Mondays at 12:00 UTC.
# Cron format: cron(minutes hours day-of-month month day-of-week year)

resource "aws_cloudwatch_event_rule" "etl_schedule" {
  name                = "${var.project_name}-etl-schedule"
  description         = "Weekly trigger for the incremental ETL Glue job"
  schedule_expression = "cron(0 12 ? * MON *)"
}

resource "aws_cloudwatch_event_target" "etl_schedule_target" {
  rule      = aws_cloudwatch_event_rule.etl_schedule.name
  target_id = "RunGlueETLJob"
  arn       = aws_glue_job.etl.arn
  role_arn  = data.aws_iam_role.lab_role.arn
}
