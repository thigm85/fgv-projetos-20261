import boto3
import time
import os
import urllib.request
from dotenv import load_dotenv

load_dotenv()

# Configurações do ambiente
DB_INSTANCE_IDENTIFIER = os.getenv("DB_INSTANCE_IDENTIFIER")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_ENGINE = "mysql"
DB_INSTANCE_CLASS = "db.t3.micro"
ALLOCATED_STORAGE = 20

rds = boto3.client('rds', region_name='us-east-1')
ec2 = boto3.client('ec2', region_name='us-east-1')

def get_public_ip():
    """Obtém o IP público atual da máquina executando o script."""
    try:
        return urllib.request.urlopen('https://checkip.amazonaws.com').read().decode('utf-8').strip()
    except Exception as e:
        print(f"Erro ao obter IP público: {e}")
        return None

def get_security_group():
    """Busca o Security Group 'default' da VPC padrão."""
    print("Buscando Security Group 'default'...")
    try:
        vpcs = ec2.describe_vpcs(Filters=[{'Name': 'isDefault', 'Values': ['true']}])
        vpc_id = vpcs['Vpcs'][0]['VpcId']
        
        sgs = ec2.describe_security_groups(
            Filters=[
                {'Name': 'vpc-id', 'Values': [vpc_id]},
                {'Name': 'group-name', 'Values': ['default']}
            ]
        )
        return sgs['SecurityGroups'][0]['GroupId']
    except Exception as e:
        print(f"Erro ao buscar Security Group: {e}")
        return None

def authorize_access(sg_id):
    """Adiciona regra de entrada para o IP atual na porta 3306."""
    ip = get_public_ip()
    if not ip:
        return
    
    print(f"Liberando acesso para o IP {ip} no Security Group {sg_id}...")
    try:
        ec2.authorize_security_group_ingress(
            GroupId=sg_id,
            IpPermissions=[
                {
                    'IpProtocol': 'tcp',
                    'FromPort': 3306,
                    'ToPort': 3306,
                    'IpRanges': [{'CidrIp': f"{ip}/32", 'Description': 'Acesso script python'}]
                }
            ]
        )
        print("Regra de acesso adicionada com sucesso!")
    except ec2.exceptions.ClientError as e:
        if 'InvalidPermission.Duplicate' in str(e):
            print("Aviso: O seu IP já tem acesso liberado neste Security Group.")
        else:
            print(f"Erro ao adicionar regra de acesso: {e}")

def provision_rds(sg_id):
    """Cria a instância RDS MySQL."""
    print(f"Provisionando RDS {DB_INSTANCE_IDENTIFIER}...")
    try:
        rds.create_db_instance(
            DBInstanceIdentifier=DB_INSTANCE_IDENTIFIER,
            AllocatedStorage=ALLOCATED_STORAGE,
            DBInstanceClass=DB_INSTANCE_CLASS,
            Engine=DB_ENGINE,
            MasterUsername=DB_USER,
            MasterUserPassword=DB_PASSWORD,
            VpcSecurityGroupIds=[sg_id],
            PubliclyAccessible=True,
            DBName=DB_NAME,
            BackupRetentionPeriod=0,
            MultiAZ=False
        )
        print("Criação da instância iniciada com sucesso!")
    except rds.exceptions.DBInstanceAlreadyExistsFault:
        print("Aviso: Instância RDS já existe.")
    except Exception as e:
        print(f"Erro ao criar instância RDS: {e}")

def update_env_file(endpoint):
    """Atualiza ou adiciona a variável DB_HOST no arquivo .env."""
    env_path = ".env"
    lines = []
    found = False
    
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            lines = f.readlines()
    
    with open(env_path, 'w') as f:
        for line in lines:
            if line.startswith("DB_HOST="):
                f.write(f"DB_HOST={endpoint}\n")
                found = True
            else:
                f.write(line)
        
        if not found:
            f.write(f"\nDB_HOST={endpoint}\n")
    
    print(f"Arquivo .env atualizado com DB_HOST={endpoint}")

def wait_for_rds():
    """Aguarda a instância ficar disponível e retorna o endpoint."""
    print("Aguardando instância ficar 'available' (pode levar alguns minutos)...")
    while True:
        try:
            desc = rds.describe_db_instances(DBInstanceIdentifier=DB_INSTANCE_IDENTIFIER)
            status = desc['DBInstances'][0]['DBInstanceStatus']
            print(f"Status atual: {status}")
            
            if status == 'available':
                endpoint = desc['DBInstances'][0]['Endpoint']['Address']
                print(f"\nRDS PRONTO!")
                return endpoint
            
            time.sleep(30)
        except Exception as e:
            print(f"Erro ao verificar status: {e}")
            time.sleep(30)

if __name__ == "__main__":
    sg_id = get_security_group()
    if sg_id:
        authorize_access(sg_id)
        provision_rds(sg_id)
        endpoint = wait_for_rds()
        if endpoint:
            update_env_file(endpoint)
            print("\nSetup concluído! Agora você pode rodar o run_ddl.py")
    else:
        print("Falha ao obter Security Group. Abortando.")
