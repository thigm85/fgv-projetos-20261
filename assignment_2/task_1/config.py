import os

# RDS Configuration
RDS_INSTANCE_IDENTIFIER = "classic-models-db"
RDS_DB_NAME = "classicmodels"
RDS_MASTER_USERNAME = "admin"
RDS_MASTER_PASSWORD = os.environ.get("RDS_PASSWORD", "ClassicModels2026!")
RDS_REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
RDS_PORT = 3306

# Watermark configuration
WATERMARK_TABLE = "etl_watermark"
PIPELINE_NAME = "classicmodels_sales"