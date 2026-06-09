#!/usr/bin/env python3
import json
import time
import urllib.request
import configparser
import boto3
from botocore.exceptions import ClientError, NoCredentialsError

CONFIG = {
    "db_instance_id":   "classicmodels-db",
    "db_name":          "classicmodels",
    "db_user":          "admin",
    "db_password":      "FGV_Projetos_2026!",
    "db_class":         "db.t3.micro",
    "db_engine":        "mysql",
    "db_engine_version":"8.0",
    "allocated_storage": 20,
    "region":           "us-east-1",
    "sg_name":          "rds-classicmodels-sg",
    "vpc_id":           "",
}

def info(msg):  print(f"[INFO] {msg}")
def warn(msg):  print(f"[AVISO] {msg}")
def error(msg): print(f"[ERRO] {msg}"); raise SystemExit(1)
def step(msg):  print(f"[PASSO] {msg}")

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

    # Sempre tenta autorizar o IP atual para o caso do IP ter mudado
    cidr = f"{my_ip}/32"
    info(f"Tentando liberar porta 3306 para o IP: {cidr}")
    try:
        ec2.authorize_security_group_ingress(
            GroupId=sg_id,
            IpPermissions=[{
                "IpProtocol": "tcp",
                "FromPort":   3306,
                "ToPort":     3306,
                "IpRanges":   [{"CidrIp": cidr, "Description": f"Acesso {time.time()}"}],
            }],
        )
        info(f"Regra de acesso para {cidr} adicionada.")
    except ClientError as e:
        if e.response["Error"]["Code"] == "InvalidPermission.Duplicate":
            info("O IP já tem acesso autorizado.")
        else:
            warn(f"Erro ao autorizar IP: {e}")

    return sg_id


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
    info(f"DB Subnet Group criado com {len(subnet_ids)} subnet(s).")
    return subnet_group_name


def create_rds_instance(rds, cfg: dict, sg_id: str, subnet_group_name: str):
    try:
        resp = rds.describe_db_instances(DBInstanceIdentifier=cfg["db_instance_id"])
        status = resp["DBInstances"][0]["DBInstanceStatus"]
        info(f"Instância já existe com status: {status}")
        return
    except ClientError as e:
        if e.response["Error"]["Code"] != "DBInstanceNotFound":
            raise

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
        MultiAZ               = False,
        PubliclyAccessible    = True,
        VpcSecurityGroupIds   = [sg_id],
        DBSubnetGroupName     = subnet_group_name,
        BackupRetentionPeriod = 0,
        DeletionProtection    = False,
    )
    info("Instância em criação. Aguardando ficar disponível...")


def wait_for_available(rds, db_instance_id: str):
    step("Aguardando status 'available'...")
    waiter = rds.get_waiter("db_instance_available")
    dots = 0
    while True:
        try:
            resp = rds.describe_db_instances(DBInstanceIdentifier=db_instance_id)
            status = resp["DBInstances"][0]["DBInstanceStatus"]
            info(f"Status atual: {status}")
            if status == "available":
                break
            dots += 1
            time.sleep(15)
        except KeyboardInterrupt:
            print("\nInterrompido pelo usuário.")
            raise SystemExit(0)


def save_connection_env(host: str, port: int, cfg: dict):
    content = (
        "# Gerado automaticamente por provisionamento.py\n"
        f"RDS_HOST={host}\n"
        f"RDS_PORT={port}\n"
        f"RDS_DB={cfg['db_name']}\n"
        f"RDS_USER={cfg['db_user']}\n"
        f"RDS_PASSWORD={cfg['db_password']}\n"
    )
    with open("rds_connection.env", "w") as f:
        f.write(content)
    info("Conexão salva em: rds_connection.env")

def main():
    cfg = CONFIG

    print(f"Criando o provisionamento RDS para classicmodels")

    step("Verificando credenciais AWS...")
    try:
        sts = boto3.client("sts", region_name=cfg["region"])
        identity = sts.get_caller_identity()
        info(f"Conta AWS: {identity['Account']}")
    except NoCredentialsError:
        error(
            "Credenciais AWS não configuradas."
        )

    ec2 = boto3.client("ec2",  region_name=cfg["region"])
    rds = boto3.client("rds",  region_name=cfg["region"])

    vpc_id = cfg["vpc_id"] or get_default_vpc(ec2)
    info(f"VPC: {vpc_id}")

    my_ip = get_my_ip()

    step("Verificando Security Group...")
    sg_id = get_or_create_security_group(ec2, vpc_id, cfg["sg_name"], my_ip)

    subnet_group_name = f"{cfg['db_instance_id']}-subnet-group"
    step("Verificando DB Subnet Group...")
    get_or_create_subnet_group(rds, ec2, vpc_id, subnet_group_name)

    step("Verificando instância RDS...")
    create_rds_instance(rds, cfg, sg_id, subnet_group_name)

    wait_for_available(rds, cfg["db_instance_id"])

    resp = rds.describe_db_instances(DBInstanceIdentifier=cfg["db_instance_id"])
    endpoint = resp["DBInstances"][0]["Endpoint"]
    host = endpoint["Address"]
    port = endpoint["Port"]

    save_connection_env(host, port, cfg)

    print(f"RDS provisionado com sucesso")

if __name__ == "__main__":
    main()