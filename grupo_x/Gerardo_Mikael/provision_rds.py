import boto3
import time
import os
from dotenv import load_dotenv

rds = boto3.client("rds", region_name="us-east-1")
print(rds.describe_db_instances())

'''
load_dotenv()

# Config
DB_INSTANCE_ID = os.getenv('DB_INSTANCE_ID')
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')
DB_NAME = os.getenv('DB_NAME')
DB_CLASS = os.getenv('DB_CLASS')
ENGINE = os.getenv('ENGINE')

rds = boto3.client("rds")

def create_db():
    try:
        print("Criando instância RDS...")

        rds.create_db_instance(
            DBInstanceIdentifier=DB_INSTANCE_ID,
            AllocatedStorage=20,
            DBInstanceClass=DB_CLASS,
            Engine=ENGINE,
            MasterUsername=DB_USER,
            MasterUserPassword=DB_PASSWORD,
            DBName=DB_NAME,
            PubliclyAccessible=True
        )

        print("Instância criada. Aguardando disponibilidade...")

    except Exception as e:
        print(f"Erro ao criar DB: {e}")
        return False

    return True


def wait_for_db():
    print("Esperando RDS...")

    while True:
        response = rds.describe_db_instances(DBInstanceIdentifier=DB_INSTANCE_ID)
        status = response["DBInstances"][0]["DBInstanceStatus"]

        print(f"Status atual: {status}")

        if status == "available":
            print("RDS disponível!")
            break

        time.sleep(20)


def get_endpoint():
    response = rds.describe_db_instances(DBInstanceIdentifier=DB_INSTANCE_ID)
    endpoint = response["DBInstances"][0]["Endpoint"]["Address"]

    print(f"Endpoint do banco: {endpoint}")
    return endpoint


if __name__ == "__main__":
    if create_db():
        wait_for_db()
        get_endpoint()'''