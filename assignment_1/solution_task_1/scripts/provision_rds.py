"""
Provisiona uma instancia MySQL no Amazon RDS.

Execute a partir de assignment_1/solution_task_1/:
    python scripts/provision_rds.py [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
from time import sleep
from urllib.request import urlopen

import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[1]
ENDPOINT_CACHE_FILE = ROOT_DIR / ".rds_endpoint.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Provisiona uma instancia RDS MySQL")
    parser.add_argument("--dry-run", action="store_true", help="Somente imprime as acoes")
    parser.add_argument(
        "--wait",
        action="store_true",
        help="Aguarda a instancia ficar disponivel e imprime endpoint",
    )
    return parser.parse_args()


def required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"Variavel obrigatoria ausente: {name}")
    return value


def read_settings() -> dict[str, str]:
    return {
        "region": required_env("AWS_REGION"),
        "identifier": required_env("RDS_INSTANCE_IDENTIFIER"),
        "db_class": required_env("RDS_DB_INSTANCE_CLASS"),
        "storage": required_env("RDS_ALLOCATED_STORAGE"),
        "engine": required_env("RDS_ENGINE"),
        "engine_version": required_env("RDS_ENGINE_VERSION"),
        "username": required_env("RDS_MASTER_USERNAME"),
        "password": required_env("RDS_MASTER_PASSWORD"),
        "port": required_env("RDS_PORT"),
    }


def maybe_get_instance(rds_client, identifier: str) -> dict | None:
    try:
        response = rds_client.describe_db_instances(DBInstanceIdentifier=identifier)
        return response["DBInstances"][0]
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "DBInstanceNotFound":
            return None
        raise


def create_instance(rds_client, settings: dict[str, str]) -> None:
    rds_client.create_db_instance(
        DBInstanceIdentifier=settings["identifier"],
        DBInstanceClass=settings["db_class"],
        Engine=settings["engine"],
        EngineVersion=settings["engine_version"],
        AllocatedStorage=int(settings["storage"]),
        MasterUsername=settings["username"],
        MasterUserPassword=settings["password"],
        Port=int(settings["port"]),
        PubliclyAccessible=True,
        BackupRetentionPeriod=0,
        StorageType="gp3",
    )


def version_key(version: str) -> tuple[int, ...]:
    parts = re.findall(r"\d+", version)
    return tuple(int(part) for part in parts) if parts else (0,)


def get_latest_supported_version(rds_client, engine: str) -> str:
    paginator = rds_client.get_paginator("describe_db_engine_versions")
    versions: set[str] = set()
    for page in paginator.paginate(Engine=engine):
        for item in page.get("DBEngineVersions", []):
            value = item.get("EngineVersion")
            if value:
                versions.add(value)
    if not versions:
        raise RuntimeError(f"Nenhuma versao disponivel para engine {engine}.")
    return max(versions, key=version_key)


def create_instance_with_fallback(rds_client, settings: dict[str, str]) -> None:
    try:
        create_instance(rds_client, settings)
    except ClientError as exc:
        code = exc.response["Error"].get("Code", "")
        message = exc.response["Error"].get("Message", "")
        invalid_version = code == "InvalidParameterCombination" and "Cannot find version" in message
        if not invalid_version:
            raise

        configured_version = settings["engine_version"]
        latest = get_latest_supported_version(rds_client, settings["engine"])
        if latest == configured_version:
            raise

        print(
            "Versao configurada nao disponivel nesta regiao: "
            f"{configured_version}. Usando fallback automatico: {latest}."
        )
        settings["engine_version"] = latest
        create_instance(rds_client, settings)


def save_endpoint(endpoint: str, port: int) -> None:
    ENDPOINT_CACHE_FILE.write_text(
        json.dumps({"endpoint": endpoint, "port": port}, indent=2), encoding="utf-8"
    )


def discover_public_cidr() -> str:
    with urlopen("https://checkip.amazonaws.com", timeout=5) as response:
        ip = response.read().decode("utf-8").strip()
    if not ip:
        raise RuntimeError("Nao foi possivel descobrir IP publico para configurar Security Group.")
    return f"{ip}/32"


def ensure_security_group_ingress(ec2_client, db_instance: dict, port: int) -> None:
    sg_entries = db_instance.get("VpcSecurityGroups", [])
    if not sg_entries:
        print("Nenhum Security Group associado ao RDS; pulando configuracao de ingress.")
        return

    group_id = sg_entries[0]["VpcSecurityGroupId"]
    cidr = os.getenv("RDS_INGRESS_CIDR") or discover_public_cidr()
    print(f"Garantindo regra SG ingress: group={group_id}, tcp/{port}, cidr={cidr}")

    sg = ec2_client.describe_security_groups(GroupIds=[group_id])["SecurityGroups"][0]
    already_allowed = False
    for permission in sg.get("IpPermissions", []):
        from_port = permission.get("FromPort")
        to_port = permission.get("ToPort")
        if permission.get("IpProtocol") == "tcp" and from_port == port and to_port == port:
            for ip_range in permission.get("IpRanges", []):
                if ip_range.get("CidrIp") == cidr:
                    already_allowed = True
                    break
        if already_allowed:
            break

    if already_allowed:
        print("Regra de ingress ja existe para esse CIDR.")
        return

    try:
        ec2_client.authorize_security_group_ingress(
            GroupId=group_id,
            IpPermissions=[
                {
                    "IpProtocol": "tcp",
                    "FromPort": port,
                    "ToPort": port,
                    "IpRanges": [{"CidrIp": cidr, "Description": "Task1 local access"}],
                }
            ],
        )
        print("Regra de ingress adicionada com sucesso.")
    except ClientError as exc:
        code = exc.response["Error"].get("Code", "")
        if code in {"InvalidPermission.Duplicate", "InvalidPermission.Malformed"}:
            print(f"Aviso ao criar regra de ingress ({code}): {exc}")
            return
        raise


def wait_for_endpoint(rds_client, identifier: str) -> tuple[str, int]:
    while True:
        db = maybe_get_instance(rds_client, identifier)
        if not db:
            raise RuntimeError("Instancia nao encontrada durante espera.")
        status = db["DBInstanceStatus"]
        print(f"Status atual: {status}")
        endpoint_info = db.get("Endpoint")
        if status == "available" and endpoint_info:
            return endpoint_info["Address"], endpoint_info["Port"]
        sleep(20)


def main() -> None:
    load_dotenv(ROOT_DIR / ".env")
    args = parse_args()
    settings = read_settings()

    print("Configuracao lida com sucesso.")
    print(f"Instancia: {settings['identifier']} | Regiao: {settings['region']}")

    if args.dry_run:
        print("Dry-run habilitado: nenhuma chamada de criacao sera executada.")
        return

    rds = boto3.client("rds", region_name=settings["region"])
    ec2 = boto3.client("ec2", region_name=settings["region"])
    instance = maybe_get_instance(rds, settings["identifier"])
    if instance is None:
        print("Instancia nao existe. Criando...")
        create_instance_with_fallback(rds, settings)
        print("Solicitacao de criacao enviada.")
    else:
        print(f"Instancia ja existe com status: {instance['DBInstanceStatus']}")

    if args.wait:
        endpoint, port = wait_for_endpoint(rds, settings["identifier"])
        current_instance = maybe_get_instance(rds, settings["identifier"])
        if current_instance:
            ensure_security_group_ingress(ec2, current_instance, int(settings["port"]))
        save_endpoint(endpoint, port)
        print(f"Endpoint salvo em {ENDPOINT_CACHE_FILE}")
        print(f"RDS_ENDPOINT={endpoint}")


if __name__ == "__main__":
    main()
