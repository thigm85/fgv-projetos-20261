import os
import boto3
from dotenv import load_dotenv

load_dotenv()

# Config from .env
DB_IDENTIFIER = os.getenv('DB_IDENTIFIER')
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')
SECURITY_GROUP_ID = os.getenv('SECURITY_GROUP_ID')

def create_rds_instance():
    # Simple validation
    if not all([DB_IDENTIFIER, DB_USER, DB_PASSWORD, SECURITY_GROUP_ID]):
        print("Missing environment variables")
        return

    rds_client = boto3.client('rds', region_name='us-east-1')
    try:
        response = rds_client.create_db_instance(
            DBInstanceIdentifier=DB_IDENTIFIER,
            AllocatedStorage=20,
            DBInstanceClass='db.t3.micro',
            Engine='mysql',
            MasterUsername=DB_USER,
            MasterUserPassword=DB_PASSWORD,
            VpcSecurityGroupIds=[SECURITY_GROUP_ID],
            PubliclyAccessible=True
        )
        
        print(f"Instance '{DB_IDENTIFIER}' is being created...")
        
        waiter = rds_client.get_waiter('db_instance_available')
        waiter.wait(DBInstanceIdentifier=DB_IDENTIFIER)
        
        print("Instance created successfully.")
        
        # Connection endpoint
        instance_info = rds_client.describe_db_instances(DBInstanceIdentifier=DB_IDENTIFIER)
        endpoint = instance_info['DBInstances'][0]['Endpoint']['Address']
        
        print(f"Connection Endpoint: {endpoint}")

    except Exception as e:
        print(f"Error creating RDS instance: {e}")

if __name__ == "__main__":
    create_rds_instance()