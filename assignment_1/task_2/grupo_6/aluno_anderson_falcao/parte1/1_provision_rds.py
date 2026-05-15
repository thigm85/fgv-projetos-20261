"""
Provisionamento da instância MySQL no Amazon RDS
"""

import boto3
import json
import os
import time
import urllib.request
from botocore.exceptions import ClientError
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------
# CONFIGURAÇÕES
# ---------------------------------------------
CONFIG = {
    "region":              "us-east-1",
    "db_instance_id":      "classicmodels-db",
    "db_name":             "classicmodels",
    "master_username":     os.getenv("USERNAME"),
    "master_password":     os.getenv("PASSWORD"),
    "instance_class":      "db.t3.micro",       # elegível ao Free Tier
    "engine_version":      "8.0",
    "allocated_storage":   20,                  # GB
    "publicly_accessible": True,                # necessário para acesso local
    "credentials_file":    "rds_credentials.json",
}
# ---------------------------------------------


# --- Validação de configuração obrigatória ---
def validate_config(cfg: dict) -> None:
    """
    Garante que variáveis obrigatórias estão presentes antes de chamar a AWS.
    Evita falhas crípticas dentro do boto3 quando USERNAME/PASSWORD não estão no .env
    """
    missing = [k for k in ("master_username", "master_password") if not cfg.get(k)]
    if missing:
        raise RuntimeError(
            f"Variáveis de ambiente obrigatórias ausentes: {', '.join(missing)}\n"
            "  Crie um arquivo .env com USERNAME=<seu_usuario> e PASSWORD=<sua_senha>"
        )


# --- Obtém o IP público atual para regra /32 ---
def get_my_public_ip() -> str:
    """
    Retorna o IP público da máquina local para criar regra de SG restrita (/32).
    Muito mais seguro que abrir 0.0.0.0/0 para toda a internet.
    """
    try:
        with urllib.request.urlopen("https://api.ipify.org", timeout=5) as resp:
            ip = resp.read().decode().strip()
            print(f"  IP público detectado: {ip}")
            return ip
    except Exception:
        # Fallback: solicita ao usuário (não deixa cair para 0.0.0.0/0)
        ip = input(
            "  Não foi possível detectar IP automaticamente.\n"
            "  Informe seu IP público (ex: 200.150.100.50): "
        ).strip()
        if not ip:
            raise RuntimeError("IP público não fornecido. Abortando por segurança.")
        return ip


def get_or_create_security_group(ec2, group_name: str) -> str:
    """
    Retorna o ID de um SG que libera MySQL (3306) APENAS para o IP atual (/32).

    MUDANÇA EM RELAÇÃO À VERSÃO ANTERIOR:
      - Antes: abria 0.0.0.0/0 (toda a internet)
      - Agora: restringe ao IP público atual (/32)
    """
    my_ip = get_my_public_ip()
    my_cidr = f"{my_ip}/32"

    try:
        resp = ec2.describe_security_groups(GroupNames=[group_name])
        sg_id = resp["SecurityGroups"][0]["GroupId"]
        print(f"  Security group já existe: {sg_id}")

        # Garante que a regra para o IP atual existe (pode ter mudado de sessão para sessão)
        _ensure_ingress_rule(ec2, sg_id, my_cidr)
        return sg_id
    except ClientError:
        pass  # não existe ainda, vamos criar

    vpc_id = ec2.describe_vpcs(
        Filters=[{"Name": "isDefault", "Values": ["true"]}]
    )["Vpcs"][0]["VpcId"]

    sg = ec2.create_security_group(
        GroupName=group_name,
        Description="Acesso MySQL para o laboratorio classicmodels",
        VpcId=vpc_id,
    )
    sg_id = sg["GroupId"]

    ec2.authorize_security_group_ingress(
        GroupId=sg_id,
        IpPermissions=[
            {
                "IpProtocol": "tcp",
                "FromPort": 3306,
                "ToPort": 3306,
                "IpRanges": [
                    {
                        "CidrIp": my_cidr,
                        "Description": f"MySQL lab - IP restrito ({int(time.time())})",
                    }
                ],
            }
        ],
    )
    print(f"  Security group criado com acesso restrito a {my_cidr}: {sg_id}")
    return sg_id


def _ensure_ingress_rule(ec2, sg_id: str, my_cidr: str) -> None:
    """
    Adiciona regra para o IP atual se ainda não existir no SG.
    Útil quando o IP muda entre sessões de laboratório.
    """
    resp = ec2.describe_security_groups(GroupIds=[sg_id])
    existing_cidrs = {
        ip_range["CidrIp"]
        for perm in resp["SecurityGroups"][0].get("IpPermissions", [])
        if perm.get("FromPort") == 3306
        for ip_range in perm.get("IpRanges", [])
    }

    if my_cidr in existing_cidrs:
        print(f"  Regra para {my_cidr} já existe no SG.")
        return

    try:
        ec2.authorize_security_group_ingress(
            GroupId=sg_id,
            IpPermissions=[
                {
                    "IpProtocol": "tcp",
                    "FromPort": 3306,
                    "ToPort": 3306,
                    "IpRanges": [
                        {
                            "CidrIp": my_cidr,
                            "Description": f"MySQL lab - IP atualizado ({int(time.time())})",
                        }
                    ],
                }
            ],
        )
        print(f"  Regra adicionada para novo IP: {my_cidr}")
    except ClientError as e:
        if "InvalidPermission.Duplicate" in str(e):
            pass  # já existe, ok
        else:
            raise


def get_or_create_db_subnet_group(rds, ec2, vpc_id: str, group_name: str) -> str:
    """
    Obtém ou cria um DB subnet group para a VPC especificada.
    Necessário para evitar conflitos com subnet groups em VPCs deletadas.
    """
    try:
        resp = rds.describe_db_subnet_groups(DBSubnetGroupName=group_name)
        subnet_group_id = resp["DBSubnetGroups"][0]["DBSubnetGroupName"]
        print(f"  DB subnet group já existe: {subnet_group_id}")
        return subnet_group_id
    except ClientError:
        pass  # não existe, vamos criar

    # Obtém subnets disponíveis na VPC
    subnets = ec2.describe_subnets(
        Filters=[{"Name": "vpc-id", "Values": [vpc_id]}]
    )["Subnets"]

    if not subnets:
        raise RuntimeError(
            f"Nenhuma subnet encontrada na VPC {vpc_id}. "
            "Verifique a configuração da VPC."
        )

    subnet_ids = [subnet["SubnetId"] for subnet in subnets]
    print(f"  Criando DB subnet group com {len(subnet_ids)} subnet(s)...")

    rds.create_db_subnet_group(
        DBSubnetGroupName=group_name,
        DBSubnetGroupDescription="Subnet group para RDS classicmodels lab",
        SubnetIds=subnet_ids,
        Tags=[{"Key": "Project", "Value": "classicmodels-lab"}],
    )
    print(f"  DB subnet group criado: {group_name}")
    return group_name


def provision_rds(cfg: dict) -> dict:
    session = boto3.Session(region_name=cfg["region"])
    rds = session.client("rds")
    ec2 = session.client("ec2")

    # Obtém a VPC para usar com security group e DB subnet group
    vpcs_default = ec2.describe_vpcs(
        Filters=[{"Name": "isDefault", "Values": ["true"]}]
    )["Vpcs"]
    if vpcs_default:
        vpc_id = vpcs_default[0]["VpcId"]
    else:
        vpcs_all = ec2.describe_vpcs()["Vpcs"]
        if not vpcs_all:
            raise RuntimeError(
                "Nenhuma VPC encontrada. Verifique sua configuração AWS."
            )
        vpc_id = vpcs_all[0]["VpcId"]

    sg_name = f"{cfg['db_instance_id']}-sg"
    print(f"\n[1/3] Configurando security group '{sg_name}'...")
    sg_id = get_or_create_security_group(ec2, sg_name)

    # Cria DB subnet group para a VPC
    subnet_group_name = f"{cfg['db_instance_id']}-subnet-group"
    print(f"  Configurando DB subnet group '{subnet_group_name}'...")
    get_or_create_db_subnet_group(rds, ec2, vpc_id, subnet_group_name)

    # Verifica se a instância já existe
    try:
        resp = rds.describe_db_instances(DBInstanceIdentifier=cfg["db_instance_id"])
        db = resp["DBInstances"][0]
        status = db["DBInstanceStatus"]
        print(f"\n[2/3] Instância já existe (status: {status}).")

        # aguarda 'available' mesmo quando a instância já existe,
        # caso esteja em estado intermediário como 'creating' ou 'modifying'.
        if status != "available":
            print(f"      Status '{status}' - aguardando ficar disponível...")
            waiter = rds.get_waiter("db_instance_available")
            waiter.wait(
                DBInstanceIdentifier=cfg["db_instance_id"],
                WaiterConfig={"Delay": 20, "MaxAttempts": 30},
            )
            # Re-busca endpoint após waiter (pode não estar preenchido antes)
            resp = rds.describe_db_instances(DBInstanceIdentifier=cfg["db_instance_id"])
            db = resp["DBInstances"][0]

        endpoint = db.get("Endpoint", {}).get("Address", "pending")
        port = db.get("Endpoint", {}).get("Port", 3306)
        print(f"      Endpoint: {endpoint}")
        return build_credentials(cfg, endpoint, port)

    except ClientError as e:
        if "DBInstanceNotFound" not in str(e):
            raise

    print(f"\n[2/3] Criando instância RDS '{cfg['db_instance_id']}' ...")
    rds.create_db_instance(
        DBInstanceIdentifier=cfg["db_instance_id"],
        DBName=cfg["db_name"],
        MasterUsername=cfg["master_username"],
        MasterUserPassword=cfg["master_password"],
        DBInstanceClass=cfg["instance_class"],
        Engine="mysql",
        EngineVersion=cfg["engine_version"],
        AllocatedStorage=cfg["allocated_storage"],
        PubliclyAccessible=cfg["publicly_accessible"],
        VpcSecurityGroupIds=[sg_id],
        DBSubnetGroupName=subnet_group_name,
        BackupRetentionPeriod=0,   # sem backups automáticos (lab)
        MultiAZ=False,
        Tags=[{"Key": "Project", "Value": "classicmodels-lab"}],
    )

    print("\n[3/3] Aguardando instância ficar disponível (pode levar ~5 min)...")
    waiter = rds.get_waiter("db_instance_available")
    waiter.wait(
        DBInstanceIdentifier=cfg["db_instance_id"],
        WaiterConfig={"Delay": 20, "MaxAttempts": 30},
    )

    resp = rds.describe_db_instances(DBInstanceIdentifier=cfg["db_instance_id"])
    endpoint = resp["DBInstances"][0]["Endpoint"]["Address"]
    port = resp["DBInstances"][0]["Endpoint"]["Port"]
    print(f"\n   Instância disponível!")
    print(f"     Endpoint : {endpoint}")
    print(f"     Porta    : {port}")

    return build_credentials(cfg, endpoint, port)


def build_credentials(cfg: dict, endpoint: str, port: int = 3306) -> dict:
    return {
        "host":     endpoint,
        "port":     port,
        "database": cfg["db_name"],
        "username": cfg["master_username"],
        "password": cfg["master_password"],
        "region":   cfg["region"],
        "instance": cfg["db_instance_id"],
    }


def save_credentials(creds: dict, filepath: str) -> None:
    with open(filepath, "w") as f:
        json.dump(creds, f, indent=2)
    print(f"\n   Credenciais salvas em '{filepath}'")


def main():
    print("=" * 55)
    print("  Provisionamento RDS MySQL - classicmodels lab")
    print("=" * 55)

    # valida config antes de qualquer chamada AWS
    validate_config(CONFIG)

    creds = provision_rds(CONFIG)
    save_credentials(creds, CONFIG["credentials_file"])

    print("\n" + "=" * 55)
    print("  RESUMO DE ACESSO")
    print("=" * 55)
    for k, v in creds.items():
        label = k.ljust(12)
        display = "***" if k == "password" else v   # não imprime senha
        print(f"  {label}: {display}")
    print("=" * 55)


if __name__ == "__main__":
    main()