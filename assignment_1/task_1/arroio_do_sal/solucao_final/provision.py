import os
import boto3
from dotenv import load_dotenv

load_dotenv()

AWS_REGION = os.getenv('AWS_REGION')
DB_INSTANCE_ID = os.getenv('DB_INSTANCE_ID')
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')

rds = boto3.client('rds', region_name=AWS_REGION)

response = rds.create_db_instance(
    DBInstanceIdentifier=DB_INSTANCE_ID,
    AllocatedStorage=20,
    DBInstanceClass='db.t3.micro',
    Engine='mysql',
    MasterUsername=DB_USER,
    MasterUserPassword=DB_PASSWORD,
    PubliclyAccessible=True
)

print("Instância criada")
