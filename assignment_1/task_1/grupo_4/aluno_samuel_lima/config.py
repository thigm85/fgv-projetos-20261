import os
from dotenv import load_dotenv

load_dotenv()

AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

RDS_IDENTIFIER = os.getenv("RDS_DB_INSTANCE_IDENTIFIER", "classicmodels-db")
DB_USER = os.getenv("RDS_MASTER_USERNAME", "admin")
DB_PASSWORD = os.getenv("RDS_MASTER_PASSWORD")
DB_NAME = "classicmodels"
PORT = 3306
