# Agendamento: EventBridge (cron) -> Lambda -> glue:StartJobRun.
#
# EventBridge Rules não têm target nativo para Glue; o padrão suportado e usado aqui
# é uma Lambda intermediária que chama StartJobRun. A Lambda assume a LabRole (que já
# possui permissão de Glue no Learner Lab) e o EventBridge é autorizado a invocar a
# Lambda via aws_lambda_permission (policy de recurso — não cria IAM Role nova).

data "archive_file" "start_glue_job" {
  type        = "zip"
  source_file = "${path.module}/../lambda/start_glue_job.py"
  output_path = "${path.module}/build/start_glue_job.zip"
}

resource "aws_lambda_function" "start_glue_job" {
  function_name    = "${var.project_prefix}-start-glue-job"
  role             = local.lab_role_arn
  runtime          = "python3.12"
  handler          = "start_glue_job.handler"
  filename         = data.archive_file.start_glue_job.output_path
  source_code_hash = data.archive_file.start_glue_job.output_base64sha256
  timeout          = 30

  environment {
    variables = {
      GLUE_JOB_NAME = aws_glue_job.classicmodels_incremental_etl.name
    }
  }
}

resource "aws_cloudwatch_event_rule" "etl_schedule" {
  name                = "${var.project_prefix}-etl-schedule"
  description         = "Dispara o ETL incremental do classicmodels via Lambda"
  schedule_expression = var.schedule_expression
}

resource "aws_cloudwatch_event_target" "etl_lambda" {
  rule      = aws_cloudwatch_event_rule.etl_schedule.name
  target_id = "start-glue-job-lambda"
  arn       = aws_lambda_function.start_glue_job.arn
}

resource "aws_lambda_permission" "allow_eventbridge" {
  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.start_glue_job.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.etl_schedule.arn
}
