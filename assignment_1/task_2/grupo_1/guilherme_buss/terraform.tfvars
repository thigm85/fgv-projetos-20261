aws_region  = "us-east-1"
aws_profile = "default"

project_name = "classic-models-etl"
environment  = "dev"

rds_instance_identifier  = "classic-models-db"
rds_allocated_storage    = 20
rds_engine_version       = "8.0.35"
rds_instance_class       = "db.t3.micro"
enable_rds_public_access = true

db_name             = "classicmodels"
db_master_username  = "admin"

glue_job_name           = "classic-models-etl-job"
glue_job_worker_type    = "G.1X"
glue_job_num_workers    = 2

tags = {
  Project    = "ClassicModels-ETL"
  ManagedBy  = "Terraform"
  Purpose    = "DataEngineering"
  Environment = "dev"
}