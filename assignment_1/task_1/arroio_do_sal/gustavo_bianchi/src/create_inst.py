import boto3
import requests
import sys
import os

# Pra conseguir importar a config
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from config import CFG

def provision():
    session = boto3.Session(region_name=CFG.REGION)
    ec2 = session.client('ec2')
    rds = session.client('rds')

    # Criação do Security Group na Amazon
    ip = requests.get('https://checkip.amazonaws.com').text.strip()
    try:
        sg = ec2.create_security_group(GroupName=CFG.SG_NAME, Description='Acesso Local')
        sg_id = sg['GroupId']
        ec2.authorize_security_group_ingress(
            GroupId=sg_id, IpProtocol='tcp', FromPort=3306, ToPort=3306, CidrIp=f"{ip}/32"
        )
        print(f"Security Group criado: {sg_id}")
    except:
        sg_id = ec2.describe_security_groups(GroupNames=[CFG.SG_NAME])['SecurityGroups'][0]['GroupId']
        print(f"Security Group já existe: {sg_id}")

    # Cria a instância RDS
    try:
        rds.create_db_instance(
            DBInstanceIdentifier=CFG.DB_ID,
            MasterUsername=CFG.DB_USER,
            MasterUserPassword=CFG.DB_PASS,
            DBInstanceClass=CFG.DB_CLASS,
            Engine=CFG.DB_ENGINE,
            AllocatedStorage=CFG.DB_STORAGE,
            VpcSecurityGroupIds=[sg_id],
            PubliclyAccessible=True
        )
        print("Instância criada.")

        # Para pegar o endpoint da instância
        waiter = rds.get_waiter('db_instance_available')
        waiter.wait(DBInstanceIdentifier=CFG.DB_ID)
        response = rds.describe_db_instances(DBInstanceIdentifier=CFG.DB_ID)
        endpoint = response['DBInstances'][0]['Endpoint']['Address']
        print(f"Endpoint: {endpoint}")

        return endpoint

    except Exception as e:
        print(f"Erro ao criar a instância: {e}")

        # Para pegar o endpoint da instância
        waiter = rds.get_waiter('db_instance_available')
        waiter.wait(DBInstanceIdentifier=CFG.DB_ID)
        response = rds.describe_db_instances(DBInstanceIdentifier=CFG.DB_ID)
        endpoint = response['DBInstances'][0]['Endpoint']['Address']
        print(f"Endpoint: {endpoint}")

        return endpoint

# Pra atualizar o CFG automaticamente
def update_config_file(new_endpoint):
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)
    config_path = os.path.join(project_root, 'config.py')

    with open(config_path, 'r') as f:
        lines = f.readlines()
    
    with open(config_path, 'w') as f:
        for line in lines:
            if line.strip().startswith('DB_HOST ='):
                f.write(f'    DB_HOST = "{new_endpoint}"\n')
            else:
                f.write(line)
    print("Endpoint atualizado")

if __name__ == "__main__":
    endoint = provision()
    update_config_file(endoint)