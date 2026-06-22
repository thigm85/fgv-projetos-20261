#!/usr/bin/env python3
"""Provisiona ou reutiliza uma instância MySQL no RDS e publica dados de conexão."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Iterable

import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv
from aws_net import authorize_mysql_ingress, aws_error_code, format_aws_error

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)


def env_any(
    names: Iterable[str],
    default: str | None = None,
    required: bool = False,
) -> str:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    if required and not default:
        raise RuntimeError(f"Variável obrigatória ausente: {', '.join(names)}")
    return default or ""


def parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def print_aws_error(exc: ClientError) -> None:
    logger.error("%s", format_aws_error(exc))


def describe_instance(client, identifier: str):
    try:
        response = client.describe_db_instances(DBInstanceIdentifier=identifier)
        return response["DBInstances"][0]
    except ClientError as exc:
        if aws_error_code(exc) in {"DBInstanceNotFound", "DBInstanceNotFoundFault"}:
            return None
        raise


def write_json(path: str, payload: dict) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def upsert_env(path: str, values: dict[str, str]) -> None:
    env_path = Path(path)
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []

    output: list[str] = []
    touched: set[str] = set()

    for line in lines:
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

    for key, value in values.items():
        if key not in touched:
            output.append(f"{key}={value}")

    env_path.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")


def main() -> int:
    logger.info("Passo 1/8 - Carregando variáveis de ambiente")
    load_dotenv(dotenv_path=Path(__file__).with_name(".env"), override=True)

    logger.info("Passo 2/8 - Lendo configuração do RDS")
    region = env_any(["AWS_REGION", "AWS_DEFAULT_REGION"], "us-east-1")
    identifier = env_any(["RDS_DB_INSTANCE_IDENTIFIER", "DB_INSTANCE_ID"], "classicmodels-db")
    db_name = env_any(["RDS_DB_NAME", "DB_NAME", "MYSQL_DATABASE"], "classicmodels")
    username = env_any(["RDS_MASTER_USERNAME", "DB_USER", "MYSQL_USER"], "admin")
    password = env_any(["RDS_MASTER_PASSWORD", "DB_PASSWORD", "MYSQL_PASSWORD"], required=True)

    instance_class = env_any(["RDS_DB_INSTANCE_CLASS"], "db.t3.micro")
    allocated_storage = int(env_any(["RDS_ALLOCATED_STORAGE"], "20"))
    port = int(env_any(["RDS_PORT", "DB_PORT", "MYSQL_PORT"], "3306"))
    engine_version = env_any(["RDS_ENGINE_VERSION"], "8.0")
    public = parse_bool(env_any(["RDS_PUBLICLY_ACCESSIBLE"], "true"))
    wait_until_ready = parse_bool(env_any(["RDS_WAIT"], "true"))

    output_json_cfg = env_any(["RDS_OUTPUT_JSON"], "rds_connection.json")
    output_json_path = Path(output_json_cfg)
    if not output_json_path.is_absolute():
        output_json_path = Path(__file__).resolve().parent / output_json_path

    logger.info("Passo 3/8 - Conectando ao cliente RDS (%s)", region)
    client = boto3.client("rds", region_name=region)

    try:
        instance = describe_instance(client, identifier)
    except ClientError as exc:
        print_aws_error(exc)
        return 1

    if instance is None:
        logger.info("Passo 4/8 - Criando instância RDS '%s'", identifier)
        try:
            client.create_db_instance(
                DBName=db_name,
                DBInstanceIdentifier=identifier,
                AllocatedStorage=allocated_storage,
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
            print_aws_error(exc)
            return 1
    else:
        logger.info("Passo 4/8 - Reutilizando instância existente '%s'", identifier)

    if wait_until_ready:
        logger.info("Passo 5/8 - Aguardando instância ficar disponível")
        try:
            waiter = client.get_waiter("db_instance_available")
            waiter.wait(DBInstanceIdentifier=identifier)
        except ClientError as exc:
            print_aws_error(exc)
            return 1
    else:
        logger.info("Passo 5/8 - Espera desativada (RDS_WAIT=false)")

    try:
        instance = describe_instance(client, identifier)
    except ClientError as exc:
        print_aws_error(exc)
        return 1

    if not instance:
        logger.error("Instância não encontrada após provisionamento")
        return 1

    endpoint = instance.get("Endpoint", {})
    host = endpoint.get("Address")
    resolved_port = endpoint.get("Port", port)
    authorized_cidr = None

    logger.info("Passo 6/8 - Aplicando regra de rede via detect_public_ip")
    try:
        authorized_cidr = authorize_mysql_ingress(
            region,
            resolved_port,
            instance=instance,
            logger=logger,
        )
    except Exception as exc:
        logger.warning("Não foi possível autorizar ingress automático: %s", exc)

    if not host:
        logger.error(
            "Endpoint do RDS ainda indisponível para '%s'. Defina RDS_WAIT=true e execute novamente.",
            identifier,
        )
        return 1

    payload = {
        "region": region,
        "db_instance_identifier": identifier,
        "db_name": db_name,
        "host": host,
        "port": resolved_port,
        "username": username,
        "authorized_cidr": authorized_cidr,
    }

    logger.info("Passo 7/8 - Salvando saída e atualizando .env")
    write_json(str(output_json_path), payload)

    if host:
        upsert_env(
            str(Path(__file__).with_name(".env")),
            {
                "MYSQL_HOST": str(host),
                "MYSQL_PORT": str(resolved_port),
                "MYSQL_USER": username,
                "MYSQL_PASSWORD": password,
                "MYSQL_DATABASE": db_name,
            },
        )

    logger.info("Passo 8/8 - Provisionamento concluído")
    logger.info("RDS pronto para uso")
    logger.info("Resumo:\n%s", json.dumps(payload, indent=2))
    logger.info("Arquivo de conexão salvo em: %s", output_json_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
