output "rds_endpoint" {
  value = aws_db_instance.classicmodels.address
}

output "rds_port" {
  value = aws_db_instance.classicmodels.port
}

output "rds_security_group_id" {
  value = aws_security_group.rds.id
}

output "s3_bucket_name" {
  value = aws_s3_bucket.data_lake.id
}

output "glue_job_name" {
  value = aws_glue_job.etl.name
}

# Gera pipeline_info.json para os scripts Python lerem
resource "local_file" "pipeline_info" {
  filename = "${path.module}/pipeline_info.json"
  content = jsonencode({
    rds_endpoint   = aws_db_instance.classicmodels.address
    rds_port       = aws_db_instance.classicmodels.port
    rds_db_name    = "classicmodels"
    rds_admin_user = var.rds_admin_user
    s3_bucket_name = aws_s3_bucket.data_lake.id
    glue_job_name  = aws_glue_job.etl.name
  })
}
