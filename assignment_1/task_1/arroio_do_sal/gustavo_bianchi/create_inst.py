import boto3
import requests
import time
from botocore.exceptions import ClientError

class CFG:
    # Configurações de Infraestrutura
    REGION = 'us-east-1'
    SG_NAME = 'classicmodels-sg'
    
    # Configurações do Banco de Dados
    DB_ID = 'classicmodels-db'
    DB_NAME = 'classicmodels'
    DB_USER = 'admin'
    DB_PASS = 'SenhaForteBemDificil123456789' 
    DB_CLASS = 'db.t3.micro'
    DB_ENGINE = 'mysql'
    DB_STORAGE = 20

# Inicialização dos Clientes AWS
session = boto3.Session(region_name=CFG.REGION)
ec2 = session.client('ec2')
rds = session.client('rds')

def get_my_ip():
    return requests.get('https://checkip.amazonaws.com').text.strip()

def setup_security_group():
    my_ip = f"{get_my_ip()}/32"
    try:
        # Tenta criar o Security Group
        sg = ec2.create_security_group(
            GroupName=CFG.SG_NAME,
            Description='Acesso para script local de populacao de dados'
        )
        sg_id = sg['GroupId']
        
        # Adiciona regra para MySQL (Porta 3306)
        ec2.authorize_security_group_ingress(
            GroupId=sg_id,
            IpProtocol='tcp',
            FromPort=3306,
            ToPort=3306,
            CidrIp=my_ip
        )
        print(f"Security Group criado e IP {my_ip} autorizado.")
        return sg_id
    except ClientError as e:
        if 'InvalidGroup.Duplicate' in str(e):
            sg_id = ec2.describe_security_groups(
                GroupNames=[CFG.SG_NAME]
            )['SecurityGroups'][0]['GroupId']
            print(f"Usando Security Group existente: {sg_id}")
            return sg_id
        raise e

def create_rds_instance(sg_id):
    try:
        rds.create_db_instance(
            DBInstanceIdentifier=CFG.DB_ID,
            DBName=CFG.DB_NAME,
            AllocatedStorage=CFG.DB_STORAGE,
            DBInstanceClass=CFG.DB_CLASS,
            Engine=CFG.DB_ENGINE,
            MasterUsername=CFG.DB_USER,
            MasterUserPassword=CFG.DB_PASS,
            VpcSecurityGroupIds=[sg_id],
            PubliclyAccessible=True
        )
        print("Instancia criada!")
    except ClientError as e:
        if 'DBInstanceAlreadyExists' in str(e):
            print("A instância já existe!")
        else:
            print(f" Erro ao criar RDS: {e}")

if __name__ == "__main__":
    current_sg_id = setup_security_group()
    create_rds_instance(current_sg_id)