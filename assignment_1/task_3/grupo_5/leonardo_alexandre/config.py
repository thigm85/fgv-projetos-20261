"""Configuração da Task 3"""

import os

AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

# Saída do ETL da Task 2 (terraform output s3_bucket_name)
S3_BUCKET = os.getenv("TASK2_S3_BUCKET", "grupo5-task2-c81677e6")
S3_CURATED_PREFIX = os.getenv("TASK2_S3_CURATED_PREFIX", "curated")

# Database no Glue Data Catalog / Athena
GLUE_DATABASE = os.getenv("GLUE_DATABASE", "grupo5_task2_dw")
