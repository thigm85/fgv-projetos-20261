import boto3
import json
import time

# Carregando as configurações do banco de dados
with open("config/db_credentials.json", "r") as f:
    db_config = json.load(f)

DB_INSTANCE_ID = db_config["db_instance_id"]
DB_USER = db_config["db_user"]
DB_PASSWORD = db_config["db_password"]
REGION = db_config["region"]

def setup_security_group(ec2_client):
    print("Configurando o security group (firewall)...")

    # Encontrando a VPC padrão do laboratório
    vpcs = ec2_client.describe_vpcs(Filters = [{"Name": "isDefault", "Values": ["true"]}])
    vpc_id = vpcs["Vpcs"][0]["VpcId"]

    sg_name = "rds_public_sg"
    sg_id = None

    try:
        # Tentando criar um novo security group
        response = ec2_client.create_security_group(
            GroupName = sg_name,
            Description = "Security group para acesso publico ao RDS na porta 3306",
            VpcId = vpc_id,
        )

        sg_id = response["GroupId"]
        print(f"  -> Security group: '{sg_name}' criado (ID: {sg_id}).")

        # Adicionando a regra liberando a porta 3306
        ec2_client.authorize_security_group_ingress(
            GroupId = sg_id,
            IpPermissions = [{
                "IpProtocol": "tcp",
                "FromPort": 3306,
                "ToPort": 3306,
                "IpRanges": [{"CidrIp": "0.0.0.0/0", "Description": "Acesso publico"}]
            }]
        )

        print("  -> Porta 3306 liberada com sucesso.")

    except ec2_client.exceptions.ClientError as e:
        if e.response["Error"]["Code"] == "InvalidGroup.Duplicate":
            print(f"  -> O security group '{sg_name}' já existe. Buscando ID...")
            sgs = ec2_client.describe_security_groups(GroupNames = [sg_name])
            sg_id = sgs["SecurityGroups"][0]["GroupId"]
        else:
            raise e
        
    return sg_id

def create_rds_instance():
    ec2_client = boto3.client("ec2", region_name = REGION)
    rds_client = boto3.client("rds", region_name = REGION)

    # Configurando o firewall
    sg_id = setup_security_group(ec2_client)

    print(F"Iniciando o provisionamento do banco '{DB_INSTANCE_ID}'...")

    try:
        # Provisionando o banco
        rds_client.create_db_instance(
            DBInstanceIdentifier = DB_INSTANCE_ID,
            AllocatedStorage = 20,
            DBInstanceClass = "db.t3.micro",
            Engine = "mysql",
            MasterUsername = DB_USER,
            MasterUserPassword = DB_PASSWORD,
            PubliclyAccessible = True,
            VpcSecurityGroupIds = [sg_id],
        )

        print("Requisição aceita. A AWS está provisionando o banco...")

        # Pausando o script e checando periodicamente até o status mudar para "available"
        waiter = rds_client.get_waiter("db_instance_available")
        waiter.wait(DBInstanceIdentifier = DB_INSTANCE_ID)

        # Resgatando o endereço quando o banco ficar pronto
        response = rds_client.describe_db_instances(DBInstanceIdentifier = DB_INSTANCE_ID)
        endpoint = response["DBInstances"][0]["Endpoint"]["Address"]

        print("\nBanco de dados criado e disponível com sucesso.")
        
        # Salvando as configurações
        config_data = {
            "host": endpoint,
            "port": 3306,
            "database": "classicmodels",
        }

        with open("config/db_endpoint.json", "w") as f:
            json.dump(config_data, f, indent = 4)

        print("Dados de conexão salvos no arquivo 'db_endpoint.json'.")

    except Exception as e:
        print(f"Ocorreu um erro ao tentar criar a instância: \n{e}")

if __name__ == "__main__":
    create_rds_instance()