import boto3
import time

# Configurações básicas
DB_INSTANCE_ID = "meu-db"
DB_NAME = "classicmodels"
DB_USER = "admin"
DB_PASSWORD = "Senha1234!"
DB_CLASS = "db.t3.micro"
ENGINE = "mysql"

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
    print("Esperando RDS ficar disponível...")

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
        get_endpoint()