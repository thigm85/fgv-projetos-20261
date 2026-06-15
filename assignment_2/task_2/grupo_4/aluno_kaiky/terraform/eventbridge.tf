# CloudWatch Event Rules cannot invoke Glue jobs directly (PutTargets rejects the job ARN).
# Use a native Glue SCHEDULED trigger with the same cron expression instead.
resource "aws_glue_trigger" "etl_schedule" {
  count = var.eventbridge_enabled ? 1 : 0

  name              = "${local.name_prefix}-glue-schedule"
  type              = "SCHEDULED"
  schedule          = var.glue_schedule_cron
  start_on_creation = true

  actions {
    job_name = aws_glue_job.etl.name
  }
}
