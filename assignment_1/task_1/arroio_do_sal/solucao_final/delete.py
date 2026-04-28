import os
import boto3
from dotenv import load_dotenv

load_dotenv()

AWS_REGION = os.getenv('AWS_REGION')
DB_INSTANCE_ID = os.getenv('DB_INSTANCE_ID')

rds = boto3.client('rds', region_name=AWS_REGION)

rds.delete_db_instance(
    DBInstanceIdentifier=DB_INSTANCE_ID,
    SkipFinalSnapshot=True
)

print("Instância deletada")
