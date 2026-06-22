import boto3
import logging
from ..config.config import *

logging.basicConfig(level=logging.INFO)

rds = boto3.client('rds', region_name=AWS_REGION)

def create_rds():
    try:
        logging.info("Criando RDS...")

        rds.create_db_instance(
            DBName=DB_NAME,
            DBInstanceIdentifier=DB_INSTANCE_ID,
            AllocatedStorage=20,
            DBInstanceClass='db.t3.micro',
            Engine='mysql',
            MasterUsername=DB_USER,
            MasterUserPassword=DB_PASSWORD,
            PubliclyAccessible=True,
            BackupRetentionPeriod=0
        )

    except rds.exceptions.DBInstanceAlreadyExistsFault:
        logging.info("RDS já existe.")

def wait_rds():
    logging.info("Aguardando RDS...")
    waiter = rds.get_waiter('db_instance_available')
    waiter.wait(DBInstanceIdentifier=DB_INSTANCE_ID)

def get_endpoint():
    response = rds.describe_db_instances(DBInstanceIdentifier=DB_INSTANCE_ID)
    endpoint = response['DBInstances'][0]['Endpoint']['Address']
    logging.info(f"Endpoint: {endpoint}")
    return endpoint

if __name__ == "__main__":
    create_rds()
    wait_rds()
    get_endpoint()