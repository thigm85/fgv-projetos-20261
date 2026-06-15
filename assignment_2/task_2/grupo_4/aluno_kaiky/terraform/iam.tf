data "aws_iam_role" "glue" {
  name = var.glue_role_name
}

# Optional: only needed if you switch back to EventBridge Scheduler / custom targets.
resource "aws_iam_role_policy" "eventbridge_start_glue" {
  count = var.eventbridge_attach_iam_policy ? 1 : 0

  name = "${local.name_prefix}-eventbridge-glue-start"
  role = data.aws_iam_role.glue.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "GlueStartJobRun"
        Effect = "Allow"
        Action = [
          "glue:StartJobRun",
        ]
        Resource = [
          aws_glue_job.etl.arn,
          "${aws_glue_job.etl.arn}/*",
        ]
      },
    ]
  })
}
