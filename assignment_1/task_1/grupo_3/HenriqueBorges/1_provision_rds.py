import boto3
from dotenv import load_dotenv
import json
import os
import requests
from pathlib import Path

# Encontra o .env na pasta do script
env_path = Path(__file__).parent / '.env'
load_dotenv(env_path)

# AWS Credentials
access_key = os.getenv('AWS_ACCESS_KEY_ID')
secret_key = os.getenv('AWS_SECRET_ACCESS_KEY')
session_token = os.getenv('AWS_SESSION_TOKEN')
region = os.getenv('AWS_REGION')

# RDS Configuration
rds_user = os.getenv('RDS_ADMIN_USER')
rds_password = os.getenv('RDS_ADMIN_PASSWORD')
rds_instance_id = os.getenv('RDS_INSTANCE_ID')
rds_db_name = os.getenv('RDS_DB_NAME')

# AWS Clients
aws_credentials = {
    'region_name': region,
    'aws_access_key_id': access_key,
    'aws_secret_access_key': secret_key,
    'aws_session_token': session_token
}

rds_client = boto3.client('rds', **aws_credentials)
ec2_client = boto3.client('ec2', **aws_credentials)


def create_security_group():
    """
    Cria um Security Group liberando a porta 3306 para o IP atual
    """
    # Descobrir IP atual
    ip = requests.get("https://checkip.amazonaws.com").text.strip()
    print(f"IP atual: {ip}")

    # Descobrir VPC padrão
    vpcs = ec2_client.describe_vpcs(Filters=[{"Name": "isDefault", "Values": ["true"]}])
    vpc_id = vpcs["Vpcs"][0]["VpcId"]

    # Criar ou reutilizar Security Group
    try:
        sg = ec2_client.create_security_group(
            GroupName="task1-mysql-access",
            Description="Libera porta 3306 para acesso MySQL",
            VpcId=vpc_id
        )
        sg_id = sg["GroupId"]
        print(f"Security Group criado: {sg_id}")
    except ec2_client.exceptions.ClientError as e:
        if 'InvalidGroup.Duplicate' in str(e):
            # SG já existe, buscar o ID
            sgs = ec2_client.describe_security_groups(
                GroupNames=["task1-mysql-access"]
            )
            sg_id = sgs["SecurityGroups"][0]["GroupId"]
            print(f"Security Group já existe, reutilizando: {sg_id}")
        else:
            raise

    # Liberar porta 3306 para o IP atual (ignora se regra já existe)
    try:
        ec2_client.authorize_security_group_ingress(
            GroupId=sg_id,
            IpPermissions=[{
                "IpProtocol": "tcp",
                "FromPort": 3306,
                "ToPort": 3306,
                "IpRanges": [{"CidrIp": f"{ip}/32"}]
            }]
        )
        print(f"Porta 3306 liberada para {ip}")
    except ec2_client.exceptions.ClientError as e:
        if 'InvalidPermission.Duplicate' in str(e):
            print(f"Regra já existe para {ip}")
        else:
            raise

    return sg_id


def provision_rds():
    """
    Provisiona uma instância MySQL no AWS RDS
    """
    try:
        # 1. Criar Security Group
        print(" Criando Security Group...")
        sg_id = create_security_group()

        # 2. Criar instância RDS com o Security Group
        print("\n Criando instância RDS...")
        rds_client.create_db_instance(
            DBInstanceIdentifier=rds_instance_id,
            DBInstanceClass='db.t3.micro',
            Engine='mysql',
            MasterUsername=rds_user,
            MasterUserPassword=rds_password,
            AllocatedStorage=20,
            Port=3306,
            DBName=rds_db_name,
            PubliclyAccessible=True,
            StorageType='gp2',
            VpcSecurityGroupIds=[sg_id]
        )

        print(f"Instância {rds_instance_id} criada!")
        print("Aguardando ficar disponível (5-10 min)...")

        # 3. Esperar instância ficar disponível
        waiter = rds_client.get_waiter('db_instance_available')
        waiter.wait(DBInstanceIdentifier=rds_instance_id)

        print("Instância disponível!")

        # 4. Obter detalhes da instância
        instances = rds_client.describe_db_instances(DBInstanceIdentifier=rds_instance_id)
        db_instance = instances['DBInstances'][0]

        endpoint = db_instance['Endpoint']['Address']
        port = db_instance['Endpoint']['Port']

        # 5. Salvar informações em JSON
        rds_info = {
            'instance_id': rds_instance_id,
            'endpoint': endpoint,
            'port': port,
            'admin_user': rds_user,
            'database': rds_db_name,
            'region': region,
            'security_group_id': sg_id
        }

        json_path = Path(__file__).parent / 'rds_info.json'
        with open(json_path, 'w') as f:
            json.dump(rds_info, f, indent=4)

        print(f"\nInformações da instância:")
        print(f"  Endpoint: {endpoint}")
        print(f"  Porta: {port}")
        print(f"  Usuário: {rds_user}")
        print(f"  Banco: {rds_db_name}")
        print(f"  Security Group: {sg_id}")
        print(f"\nSalvo em rds_info.json")

        return rds_info

    except Exception as e:
        print(f"Erro ao provisionar RDS: {str(e)}")
        return None


if __name__ == '__main__':
    provision_rds()
