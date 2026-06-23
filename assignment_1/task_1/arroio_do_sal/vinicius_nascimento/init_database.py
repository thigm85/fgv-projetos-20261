import boto3
import time

REGION = "us-east-1"
DB_ID = "classicmodels"
USERNAME = "admin"
PASSWORD = "ArianaGrande123!"

def create_database():
    rds = boto3.client("rds", region_name=REGION)

    print("Criando instância RDS...")

    try:
        rds.create_db_instance(
            DBInstanceIdentifier=DB_ID,
            DBInstanceClass="db.t3.micro",
            Engine="mysql",
            MasterUsername=USERNAME,
            MasterUserPassword=PASSWORD,
            AllocatedStorage=20,
            PubliclyAccessible=True
        )

        print("Aguardando banco ficar disponível...")

        waiter = rds.get_waiter("db_instance_available")
        waiter.wait(DBInstanceIdentifier=DB_ID)

        response = rds.describe_db_instances(DBInstanceIdentifier=DB_ID)

        endpoint = response["DBInstances"][0]["Endpoint"]["Address"]

        print(f"Banco pronto! Endpoint: {endpoint}")

        return endpoint

    except Exception as e:
        print("Erro:", e)


if __name__ == "__main__":
    create_database()