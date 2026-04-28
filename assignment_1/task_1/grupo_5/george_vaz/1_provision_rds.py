import boto3
import os

def create_rds_instance():
    rds_client = boto3.client('rds')
    
    db_name = "classicmodels"
    db_identifier = "classicmodels-db"
    db_user = os.getenv('aws_user')
    db_password = os.getenv('aws_password')

    print(f"Iniciando a criação do banco de dados RDS '{db_identifier}'...")

    try:
        response = rds_client.create_db_instance(
            DBName=db_name,
            DBInstanceIdentifier=db_identifier,
            AllocatedStorage=20,
            DBInstanceClass="db.t3.micro",
            Engine="mysql",
            MasterUsername=db_user,
            MasterUserPassword=db_password,
            PubliclyAccessible=True
        )
        
        waiter = rds_client.get_waiter('db_instance_available')
        waiter.wait(DBInstanceIdentifier=db_identifier)
        
        instances = rds_client.describe_db_instances(DBInstanceIdentifier=db_identifier)
        endpoint = instances['DBInstances'][0]['Endpoint']['Address']
        
        print("\nBanco de dados criado com sucesso!")
        print(f"Endpoint: {endpoint}")
        print(f"Usuário: {db_user}")
        
    except Exception as e:
        print(f"Erro ao criar o RDS: {e}")

if __name__ == "__main__":
    create_rds_instance()