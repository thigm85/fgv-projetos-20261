#!/usr/bin/env python3
"""Provisiona/reutiliza instância MySQL no RDS lendo configuração do .env."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import boto3
from botocore.exceptions import ClientError


def load_dotenv(path: str = ".env") -> None:
    env_path = Path(path)
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        entry = line.strip()
        if not entry or entry.startswith("#") or "=" not in entry:
            continue
        key, value = entry.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value


def env(name: str, default: str | None = None, required: bool = False) -> str:
    value = os.getenv(name, default)
    if required and not value:
        raise RuntimeError(f"Variável obrigatória ausente: {name}")
    return value or ""


def describe_instance(client, identifier: str):
    try:
        response = client.describe_db_instances(DBInstanceIdentifier=identifier)
        return response["DBInstances"][0]
    except client.exceptions.DBInstanceNotFoundFault:
        return None


def write_connection_file(path: str, payload: dict) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def upsert_env_values(path: str, values: dict[str, str]) -> None:
    env_path = Path(path)
    existing_lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    output = []
    touched = set()

    for line in existing_lines:
        if "=" not in line or line.strip().startswith("#"):
            output.append(line)
            continue
        key, _ = line.split("=", 1)
        key = key.strip()
        if key in values:
            output.append(f"{key}={values[key]}")
            touched.add(key)
        else:
            output.append(line)

    for key, val in values.items():
        if key not in touched:
            output.append(f"{key}={val}")

    env_path.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")


def main() -> int:
    load_dotenv()

    region = env("AWS_REGION", env("AWS_DEFAULT_REGION", "us-east-1"))
    identifier = env("RDS_DB_INSTANCE_IDENTIFIER", "classicmodels-db")
    db_name = env("RDS_DB_NAME", "classicmodels")
    username = env("RDS_MASTER_USERNAME", "admin")
    password = env("RDS_MASTER_PASSWORD", required=True)
    instance_class = env("RDS_DB_INSTANCE_CLASS", "db.t3.micro")
    storage = int(env("RDS_ALLOCATED_STORAGE", "20"))
    port = int(env("RDS_PORT", "3306"))
    engine_version = env("RDS_ENGINE_VERSION", "8.0")
    public = env("RDS_PUBLICLY_ACCESSIBLE", "true").lower() == "true"
    wait = env("RDS_WAIT", "true").lower() == "true"
    output_json = env("RDS_OUTPUT_JSON", "scripts/rds_connection.json")

    client = boto3.client("rds", region_name=region)
    instance = describe_instance(client, identifier)

    if instance is None:
        print(f"Criando instância '{identifier}'...")
        try:
            client.create_db_instance(
                DBName=db_name,
                DBInstanceIdentifier=identifier,
                AllocatedStorage=storage,
                DBInstanceClass=instance_class,
                Engine="mysql",
                EngineVersion=engine_version,
                MasterUsername=username,
                MasterUserPassword=password,
                Port=port,
                PubliclyAccessible=public,
                MultiAZ=False,
                BackupRetentionPeriod=7,
                AutoMinorVersionUpgrade=True,
                StorageType="gp2",
                DeletionProtection=False,
            )
        except ClientError as exc:
            print(f"Erro ao criar instância: {exc}", file=sys.stderr)
            return 1
        if not wait:
            print("Instância em criação.")
            return 0

    if wait:
        print("Aguardando instância ficar disponível...")
        waiter = client.get_waiter("db_instance_available")
        waiter.wait(DBInstanceIdentifier=identifier)

    instance = describe_instance(client, identifier)
    endpoint = instance.get("Endpoint", {})
    data = {
        "region": region,
        "db_instance_identifier": identifier,
        "db_name": db_name,
        "host": endpoint.get("Address"),
        "port": endpoint.get("Port", port),
        "username": username,
    }
    write_connection_file(output_json, data)
    if data["host"]:
        upsert_env_values(".env", {"MYSQL_HOST": str(data["host"]), "MYSQL_PORT": str(data["port"])})

    print("RDS pronto.")
    print(json.dumps(data, indent=2))
    print(f"Arquivo salvo: {output_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
