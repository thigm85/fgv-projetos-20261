import os

# RDS Configuration
RDS_INSTANCE_IDENTIFIER = "classicmodels-mysql"
RDS_DB_NAME = "classicmodels"
RDS_MASTER_USERNAME = "admin"
RDS_MASTER_PASSWORD = os.environ.get("RDS_PASSWORD", "ClassicModels2026!")
RDS_INSTANCE_CLASS = "db.t3.micro"
RDS_ENGINE = "mysql"
RDS_ENGINE_VERSION = "8.0"
RDS_ALLOCATED_STORAGE = 20
RDS_REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
RDS_PORT = 3306

# Path to SQL file
SQL_FILE_PATH = os.path.join(os.path.dirname(__file__), "data", "mysqlsampledatabase.sql")
