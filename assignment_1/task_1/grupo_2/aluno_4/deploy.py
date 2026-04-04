import os
import time
import boto3
import pymysql
from botocore.exceptions import ClientError

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

AWS_REGION = 'us-east-1'

# configurações security group

SG_NAME = 'old-cars-db'
SG_DESC = 'Permite acesso ao MySQL'
PORTS_TO_OPEN = [
    3306, # banco
    80    # http
]

# configurações rds

DB_IDENTIFIER = 'old-cars-db'
DB_ENGINE = 'mysql'
DB_ENGINE_VERSION = '8.0'          # versão
DB_INSTANCE_TYPE = 'db.t3.micro'   # free tier
DB_ALLOCATED_STORAGE = 20          # armazenamento
DB_NAME = 'oldcars'               # nome database
DB_USER = 'admin'
DB_PASSWORD = 'EuAmoAEMAp'         # senha 
DB_PORT = 3306
DB_BACKUP_RETENTION_PERIOD = 1     # dias de backup
DB_STORAGE_TYPE = 'gp3'            # SSD de uso geral
DB_PUBLICLY_ACCESSIBLE = True      # expõe o banco para a internet

ec2_client = boto3.client('ec2', region_name=AWS_REGION)
rds_client = boto3.client('rds', region_name=AWS_REGION)

# funções de criação

def setup_security_group():
    """
        Função para criar o security group (ou reutilizar se já existir)
    """

    # busca a vpc padrão
    vpcs = ec2_client.describe_vpcs(Filters=[{'Name': 'isDefault', 'Values': ['true']}])
    vpc_id = vpcs['Vpcs'][0]['VpcId']
    
    # verifica se o sg já existe
    try:
        sgs = ec2_client.describe_security_groups(
            Filters=[
                {'Name': 'group-name', 'Values': [SG_NAME]},
                {'Name': 'vpc-id', 'Values': [vpc_id]}
            ]
        )

        if sgs['SecurityGroups']:
            print(f"Security Group '{SG_NAME}' já existe. Retornando ID.")
            return sgs['SecurityGroups'][0]['GroupId']

    except ClientError as e:
        pass

    # se não existir, ele vai criar
    try:

        sg_response = ec2_client.create_security_group(
            GroupName=SG_NAME,
            Description=SG_DESC,
            VpcId=vpc_id
        )
        sg_id = sg_response['GroupId']
        
        # lista de permissões
        ip_permissions = []
        for port in PORTS_TO_OPEN:
            ip_permissions.append({
                'IpProtocol': 'tcp', 
                'FromPort': port, 
                'ToPort': port, 
                'IpRanges': [{'CidrIp': '0.0.0.0/0'}] # aberto para o mundo
            })

        # libera as portas configuradas acima
        ec2_client.authorize_security_group_ingress(
            GroupId=sg_id,
            IpPermissions=ip_permissions
        )

        print(f"Criação do Security Group '{SG_NAME}' bem sucedida. ID: {sg_id}")
        return sg_id

    except Exception as e:
        raise Exception(f"Erro ao criar Security Group: {e}")

def get_or_create_rds_instance(sg_id):
    """
        Provisiona o banco MySQL, mas reutiliza se já existir.
    """

    # verifica se o rds já existe
    try:
        response = rds_client.describe_db_instances(DBInstanceIdentifier=DB_IDENTIFIER)
        status = response['DBInstances'][0]['DBInstanceStatus']
        
        if status == 'available':
            endpoint = response['DBInstances'][0]['Endpoint']['Address']
            print(f"Banco RDS já existe e está pronto. Endpoint: {endpoint}")
            return endpoint
        else:
            print(f"Banco RDS encontrado, mas status atual é: '{status}'. Aguardando disponibilidade...")
    
    # se não existir, ele vai criar
    except ClientError as e:
        if e.response['Error']['Code'] == 'DBInstanceNotFound':
            print("Banco RDS não encontrado. Criando instância...")

            rds_client.create_db_instance(
                DBInstanceIdentifier=DB_IDENTIFIER,
                AllocatedStorage=DB_ALLOCATED_STORAGE,
                DBInstanceClass=DB_INSTANCE_TYPE,
                Engine=DB_ENGINE,
                EngineVersion=DB_ENGINE_VERSION,
                MasterUsername=DB_USER,
                MasterUserPassword=DB_PASSWORD,
                BackupRetentionPeriod=DB_BACKUP_RETENTION_PERIOD,
                StorageType=DB_STORAGE_TYPE,
                DBName=DB_NAME,
                VpcSecurityGroupIds=[sg_id],
                PubliclyAccessible=DB_PUBLICLY_ACCESSIBLE,
                Port=DB_PORT
            )
        else:
            raise e

    print("Aguardando RDS ficar com status 'available'...")
    waiter = rds_client.get_waiter('db_instance_available')
    waiter.wait(DBInstanceIdentifier=DB_IDENTIFIER)
    
    response = rds_client.describe_db_instances(DBInstanceIdentifier=DB_IDENTIFIER)
    endpoint = response['DBInstances'][0]['Endpoint']['Address']
    print(f"RDS disponível. Endpoint: {endpoint}")
    return endpoint

def run_sql_file(endpoint, filename):
    """Executa os SQL para criar tabelas e inserir dados"""

    try:
        conn = pymysql.connect(
            host=endpoint, 
            database=DB_NAME, 
            user=DB_USER, 
            password=DB_PASSWORD,
            port=DB_PORT,
            autocommit=True
        )
        cursor = conn.cursor()
        
        sql_path = os.path.join(BASE_DIR, filename)
        with open(sql_path, 'r', encoding='utf-8') as file:
            sql_script = file.read()

        for statement in sql_script.split(';'):
            if statement.strip():
                cursor.execute(statement)

        cursor.close()
        conn.close()

        print(f"Execução de {filename} bem sucedida.")
        
    except Exception as e:
        print(f"Erro ao interagir com o banco: {e}")

# funções de destruição

def destroy_rds_instance():
    """
        Destrói a instância RDS ignorando o snapshot final.
    """

    print(f"Iniciando destruição da instância RDS '{DB_IDENTIFIER}'...")
    try:
        rds_client.delete_db_instance(
            DBInstanceIdentifier=DB_IDENTIFIER,
            SkipFinalSnapshot=True # evita criar um snapshot no momento da exclusão
        )

        print("Exclusão solicitada. Aguardando a instância ser totalmente deletada...")
        waiter = rds_client.get_waiter('db_instance_deleted')
        waiter.wait(DBInstanceIdentifier=DB_IDENTIFIER)

        print("Instância RDS deletada com sucesso.")

    except ClientError as e:
        if e.response['Error']['Code'] == 'DBInstanceNotFound':
            print(f"Instância RDS '{DB_IDENTIFIER}' não encontrada. Nada a deletar.")
        else:
            print(f"Erro ao deletar RDS: {e}")

def destroy_security_group():
    """
        Destrói o Security Group.
    """

    print(f"Iniciando destruição do Security Group '{SG_NAME}'...")
    try:
        vpcs = ec2_client.describe_vpcs(Filters=[{'Name': 'isDefault', 'Values': ['true']}])
        vpc_id = vpcs['Vpcs'][0]['VpcId']
        
        sgs = ec2_client.describe_security_groups(
            Filters=[
                {'Name': 'group-name', 'Values': [SG_NAME]},
                {'Name': 'vpc-id', 'Values': [vpc_id]}
            ]
        )
        
        if sgs['SecurityGroups']:
            sg_id = sgs['SecurityGroups'][0]['GroupId']
            ec2_client.delete_security_group(GroupId=sg_id)

            print(f"Security Group '{SG_NAME}' ({sg_id}) deletado com sucesso.")
        else:
            print(f"Security Group '{SG_NAME}' não encontrado. Nada a deletar.")
        
    # se o security group ainda estiver em uso, ele não será deletado
    except ClientError as e:
        if e.response['Error']['Code'] == 'DependencyViolation':
            print("O Security Group ainda está em uso. Certifique-se de que o RDS foi completamente deletado.")
        else:
            print(f"Erro ao deletar Security Group: {e}")

if __name__ == "__main__":

    start_time = time.time()
    print("\n1. Criando o Security Group.")
    meu_sg_id = setup_security_group()
    end_time = time.time()
    print(f"Tempo de execução: {end_time - start_time:.2f} segundos.")

    print("\n2. Criando o RDS.")
    start_time = time.time()
    endpoint = get_or_create_rds_instance(meu_sg_id)
    end_time = time.time()
    print(f"Tempo de execução: {end_time - start_time:.2f} segundos.")

    print("\n3. Criando as tabelas.")
    start_time = time.time()
    run_sql_file(endpoint, "DDL.sql")
    end_time = time.time()
    print(f"Tempo de execução: {end_time - start_time:.2f} segundos.")

    print("\n4. Inserindo os dados.")
    start_time = time.time()
    run_sql_file(endpoint, "DML.sql")
    end_time = time.time()
    print(f"Tempo de execução: {end_time - start_time:.2f} segundos.")

    # destroy_rds_instance()
    # destroy_security_group()