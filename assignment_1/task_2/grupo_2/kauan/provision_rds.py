import os
import json
import time
import urllib.request
import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from dotenv import load_dotenv

# Carrega variáveis de ambiente do arquivo .env
load_dotenv()

CONFIG = {
    "db_instance_id":   os.getenv("DB_INSTANCE_ID", "classicmodels-db"),
    "db_name":          os.getenv("DB_NAME", "classicmodels"),
    "db_user":          os.getenv("DB_USER"),
    "db_password":      os.getenv("DB_PASSWORD"),
    "db_class":         os.getenv("DB_CLASS", "db.t3.micro"),
    "db_engine":        os.getenv("DB_ENGINE", "mysql"),
    "db_engine_version":os.getenv("DB_ENGINE_VERSION", "8.0"),
    "allocated_storage": int(os.getenv("ALLOCATED_STORAGE", "20")),
    "region":           os.getenv("AWS_REGION", "us-east-1"),
    "sg_name":          os.getenv("SG_NAME", "rds-classicmodels-sg"),
    "vpc_id":           os.getenv("VPC_ID", ""),
}

def info(msg):  print(f"[INFO] {msg}")
def warn(msg):  print(f"[AVISO] {msg}")
def error(msg): print(f"[ERRO] {msg}"); raise SystemExit(1)
def step(num, total, msg): print(f"[PASSO {num}/{total}] {msg}")

def get_my_ip() -> str:
    try:
        with urllib.request.urlopen("https://checkip.amazonaws.com", timeout=5) as r:
            return r.read().decode().strip()
    except Exception:
        warn("Não foi possível detectar IP público. Usando 0.0.0.0/0.")
        return "0.0.0.0"

def get_default_vpc(ec2) -> str:
    resp = ec2.describe_vpcs(Filters=[{"Name": "isDefault", "Values": ["true"]}])
    vpcs = resp.get("Vpcs", [])
    if not vpcs:
        error("Nenhuma VPC padrão encontrada.")
    return vpcs[0]["VpcId"]

def get_or_create_security_group(ec2, vpc_id: str, sg_name: str, my_ip: str) -> str:
    try:
        resp = ec2.describe_security_groups(
            Filters=[
                {"Name": "group-name", "Values": [sg_name]},
                {"Name": "vpc-id",     "Values": [vpc_id]},
            ]
        )
        sgs = resp.get("SecurityGroups", [])

        if sgs:
            sg_id = sgs[0]["GroupId"]
            info(f"Security Group já existe: {sg_id}")
        else:
            info(f"Criando Security Group '{sg_name}'...")
            resp = ec2.create_security_group(
                GroupName=sg_name,
                Description="Acesso MySQL para instancia RDS classicmodels",
                VpcId=vpc_id,
            )
            sg_id = resp["GroupId"]
            info(f"Security Group criado: {sg_id}")

        cidr = f"{my_ip}/32"
        info(f"Configurando acesso para o IP: {cidr}")
        try:
            ec2.authorize_security_group_ingress(
                GroupId=sg_id,
                IpPermissions=[{
                    "IpProtocol": "tcp",
                    "FromPort":   3306,
                    "ToPort":     3306,
                    "IpRanges":   [{"CidrIp": cidr, "Description": f"Acesso em {time.strftime('%Y-%m-%d %H:%M:%S')}"}],
                }],
            )
        except ClientError as e:
            if e.response["Error"]["Code"] == "InvalidPermission.Duplicate":
                info("Regra de acesso já existe.")
            else:
                warn(f"Erro ao autorizar IP: {e}")
        
        return sg_id
    except ClientError as e:
        error(f"Erro ao gerenciar Security Group: {e}")

def get_or_create_subnet_group(rds, ec2, vpc_id: str, subnet_group_name: str) -> str:
    try:
        rds.describe_db_subnet_groups(DBSubnetGroupName=subnet_group_name)
        info("DB Subnet Group já existe.")
        return subnet_group_name
    except ClientError as e:
        if e.response["Error"]["Code"] != "DBSubnetGroupNotFoundFault":
            raise

    info("Criando DB Subnet Group...")
    subnets = ec2.describe_subnets(Filters=[{"Name": "vpc-id", "Values": [vpc_id]}])
    subnet_ids = [s["SubnetId"] for s in subnets["Subnets"]]
    if not subnet_ids:
        error(f"Nenhuma subnet encontrada na VPC {vpc_id}")

    rds.create_db_subnet_group(
        DBSubnetGroupName=subnet_group_name,
        DBSubnetGroupDescription=f"Subnet group para {subnet_group_name}",
        SubnetIds=subnet_ids,
    )
    info(f"DB Subnet Group criado.")
    return subnet_group_name

def ensure_rds_instance(rds, cfg: dict, sg_id: str, subnet_group_name: str):
    try:
        rds.describe_db_instances(DBInstanceIdentifier=cfg["db_instance_id"])
        info(f"Instância RDS '{cfg['db_instance_id']}' já existe.")
    except ClientError as e:
        if e.response["Error"]["Code"] == "DBInstanceNotFound":
            info(f"Criando instância RDS '{cfg['db_instance_id']}'...")
            rds.create_db_instance(
                DBInstanceIdentifier  = cfg["db_instance_id"],
                DBInstanceClass       = cfg["db_class"],
                Engine                = cfg["db_engine"],
                EngineVersion         = cfg["db_engine_version"],
                MasterUsername        = cfg["db_user"],
                MasterUserPassword    = cfg["db_password"],
                DBName                = cfg["db_name"],
                AllocatedStorage      = cfg["allocated_storage"],
                StorageType           = "gp2",
                PubliclyAccessible    = True,
                VpcSecurityGroupIds   = [sg_id],
                DBSubnetGroupName     = subnet_group_name,
                BackupRetentionPeriod = 0,
                DeletionProtection    = False,
            )
        else:
            raise

def wait_for_rds_available(rds, db_instance_id: str):
    info("Aguardando instância ficar disponível (isso pode levar alguns minutos)...")
    waiter = rds.get_waiter("db_instance_available")
    try:
        waiter.wait(
            DBInstanceIdentifier=db_instance_id,
            WaiterConfig={'Delay': 30, 'MaxAttempts': 60}
        )
        info("Instância disponível.")
    except Exception as e:
        error(f"Erro ao aguardar instância: {e}")

def save_connection_env(host: str, port: int, cfg: dict, vpc_id: str, subnet_id: str, sg_id: str):
    content = (
        "# Gerado automaticamente por provision_rds.py\n"
        f"RDS_HOST={host}\n"
        f"RDS_PORT={port}\n"
        f"RDS_DB={cfg['db_name']}\n"
        f"RDS_USER={cfg['db_user']}\n"
        f"RDS_PASSWORD={cfg['db_password']}\n"
        f"VPC_ID={vpc_id}\n"
        f"SUBNET_ID={subnet_id}\n"
        f"RDS_SG_ID={sg_id}\n"
    )
    # Salva no .env local da tarefa
    with open("rds_connection.env", "w") as f:
        f.write(content)
    info("Conexão salva em: rds_connection.env")

def main():
    total_steps = 6
    print("=== Iniciando Provisionamento RDS (Foco em Idempotência e Segurança) ===")

    step(1, total_steps, "Verificando credenciais AWS")
    try:
        sts = boto3.client("sts", region_name=CONFIG["region"])
        identity = sts.get_caller_identity()
        info(f"Conta AWS: {identity['Account']}")
    except Exception as e:
        error(f"Erro nas credenciais AWS: {e}")

    ec2 = boto3.client("ec2", region_name=CONFIG["region"])
    rds = boto3.client("rds", region_name=CONFIG["region"])

    step(2, total_steps, "Resolvendo Infra de Rede (VPC e IP)")
    vpc_id = CONFIG["vpc_id"] or get_default_vpc(ec2)
    my_ip = get_my_ip()
    
    # Busca a primeira subnet da VPC para o Glue
    subnets = ec2.describe_subnets(Filters=[{"Name": "vpc-id", "Values": [vpc_id]}])
    subnet_id = subnets["Subnets"][0]["SubnetId"]
    
    info(f"VPC: {vpc_id} | Subnet: {subnet_id} | Seu IP: {my_ip}")

    step(3, total_steps, "Garantindo Security Group")
    sg_id = get_or_create_security_group(ec2, vpc_id, CONFIG["sg_name"], my_ip)

    step(4, total_steps, "Garantindo Subnet Group")
    subnet_group_name = f"{CONFIG['db_instance_id']}-subnet-group"
    get_or_create_subnet_group(rds, ec2, vpc_id, subnet_group_name)

    step(5, total_steps, "Provisionando Instância RDS")
    ensure_rds_instance(rds, CONFIG, sg_id, subnet_group_name)
    wait_for_rds_available(rds, CONFIG["db_instance_id"])

    step(6, total_steps, "Salvando configurações de conexão")
    resp = rds.describe_db_instances(DBInstanceIdentifier=CONFIG["db_instance_id"])
    endpoint = resp["DBInstances"][0]["Endpoint"]
    save_connection_env(endpoint["Address"], endpoint["Port"], CONFIG, vpc_id, subnet_id, sg_id)

    print("\n[SUCESSO] Pipeline de infraestrutura concluído.")

if __name__ == "__main__":
    main()