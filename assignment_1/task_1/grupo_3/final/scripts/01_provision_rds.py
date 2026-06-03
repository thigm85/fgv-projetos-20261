import boto3
import os
import sys
from botocore.exceptions import ClientError

"""
Script 01: verifies the RDS instance created by Terraform.
It does not create resources to avoid drift and duplicate provisioning.
"""

db_instance_identifier = os.getenv("DB_INSTANCE_IDENTIFIER", "classicmodels-db")
region = os.getenv("AWS_REGION", "us-east-1")

rds = boto3.client("rds", region_name=region)

try:
    response = rds.describe_db_instances(DBInstanceIdentifier=db_instance_identifier)
except ClientError as exc:
    print(f"[ERRO] Nao foi possivel localizar a instancia '{db_instance_identifier}'.")
    print("Execute 'terraform apply' antes deste script.")
    print(f"Detalhe AWS: {exc}")
    sys.exit(1)

db = response["DBInstances"][0]
status = db["DBInstanceStatus"]
endpoint = db.get("Endpoint", {}).get("Address", "<ainda sem endpoint>")
port = db.get("Endpoint", {}).get("Port", "<sem porta>")

print(f"Instancia: {db_instance_identifier}")
print(f"Status: {status}")
print(f"Endpoint: {endpoint}")
print(f"Porta: {port}")

if status != "available":
    print("[AVISO] A instancia ainda nao esta 'available'. Aguarde alguns minutos.")
