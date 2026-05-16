import boto3
import os
import sys
from botocore.exceptions import ClientError
from typing import Optional

"""Script 01: valida e aguarda RDS provisionado via Terraform (idempotente)."""


def env_any(names, default=None, required=False):
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    if required and default is None:
        raise RuntimeError(f"Variavel obrigatoria ausente: {', '.join(names)}")
    return default


def log(step: str, msg: str) -> None:
    print(f"[{step}] {msg}")


def get_instance(rds, identifier: str) -> Optional[dict]:
    try:
        response = rds.describe_db_instances(DBInstanceIdentifier=identifier)
        return response["DBInstances"][0]
    except ClientError as exc:
        if exc.response["Error"]["Code"] in {"DBInstanceNotFound", "DBInstanceNotFoundFault"}:
            return None
        raise

db_instance_identifier = env_any(["DB_INSTANCE_IDENTIFIER"], default="classicmodels-db")
region = env_any(["AWS_REGION", "AWS_DEFAULT_REGION"], default="us-east-1")
dry_run = env_any(["DRY_RUN"], default="0") == "1"

rds = boto3.client("rds", region_name=region)

log("1/4", f"Verificando instancia '{db_instance_identifier}' em {region}")
db = get_instance(rds, db_instance_identifier)
if db is None:
    log("ERRO", f"Instancia '{db_instance_identifier}' nao encontrada.")
    log("ERRO", "Execute 'terraform apply' antes deste script.")
    sys.exit(1)

status = db["DBInstanceStatus"]
endpoint = db.get("Endpoint", {}).get("Address", "<ainda sem endpoint>")
port = db.get("Endpoint", {}).get("Port", "<sem porta>")

log("2/4", f"Status atual: {status}")
if dry_run:
    log("3/4", "DRY_RUN=1 ativo; nao aguardara waiter.")
else:
    if status != "available":
        log("3/4", "Aguardando estado 'available' com timeout explicito...")
        waiter = rds.get_waiter("db_instance_available")
        waiter.wait(DBInstanceIdentifier=db_instance_identifier, WaiterConfig={"Delay": 20, "MaxAttempts": 45})
        db = get_instance(rds, db_instance_identifier)
        status = db["DBInstanceStatus"]
        endpoint = db.get("Endpoint", {}).get("Address", "<ainda sem endpoint>")
        port = db.get("Endpoint", {}).get("Port", "<sem porta>")

log("4/4", f"Instancia: {db_instance_identifier}")
print(f"Status final: {status}")
print(f"Endpoint: {endpoint}")
print(f"Porta: {port}")
