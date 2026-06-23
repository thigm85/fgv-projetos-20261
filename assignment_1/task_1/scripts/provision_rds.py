#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
import sys
import urllib.request

import boto3
from botocore.exceptions import ClientError, WaiterError

from common import (
    ConfigError,
    DEFAULT_ENV_FILE,
    get_bool_env,
    get_env,
    get_int_env,
    load_env_file,
    require_env,
    resolve_env_path,
    write_env_updates,
)

# Argumentos adicionais que são passadaos ao executar o módulo
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Provisiona uma instância MySQL no Amazon RDS para o banco classicmodels."
    )
    parser.add_argument(
        "--env-file",
        default=str(DEFAULT_ENV_FILE),
        help="Caminho para o arquivo .env.",
    )
    parser.add_argument(
        "--wait-timeout",
        type=int,
        default=3600,
        help="Tempo máximo de espera, em segundos, até a instância ficar available.",
    )
    parser.add_argument(
        "--skip-security-group",
        action="store_true",
        help="Não cria nem gerencia security group automaticamente.",
    )
    parser.add_argument(
        "--no-write-env",
        action="store_true",
        help="Não atualiza o arquivo .env com endpoint e configurações do MySQL.",
    )
    return parser.parse_args()

# Parse para ler info do arquivo .env
def parse_security_group_ids(raw_value: str | None) -> list[str]:
    if not raw_value:
        return []
    return [item.strip() for item in raw_value.split(",") if item.strip()]


# Tenta descobrir de forma automática qual é o email público
def detect_public_ip() -> str:
    urls = ("https://checkip.amazonaws.com", "https://api.ipify.org")
    last_error: Exception | None = None

    for url in urls:
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                return response.read().decode("utf-8").strip()
        except Exception as exc:  # noqa: BLE001
            last_error = exc

    raise ConfigError(
        "Unable to detect public IP automatically. Set RDS_ALLOWED_CIDR in .env."
    ) from last_error

# Conecta com o cloud onde os recursos do RDS são criado e configurados
def get_default_vpc_id(ec2_client) -> str:
    response = ec2_client.describe_vpcs(
        Filters=[{"Name": "isDefault", "Values": ["true"]}]
    )
    vpcs = response.get("Vpcs", [])
    if not vpcs:
        raise ConfigError(
            "No default VPC found. Set RDS_VPC_SECURITY_GROUP_IDS in .env "
            "or create the RDS instance in a pre-configured network."
        )
    return vpcs[0]["VpcId"]


def ingress_rule_exists(
    permissions: list[dict[str, object]], cidr: str, port: int
) -> bool:
    for permission in permissions:
        from_port = permission.get("FromPort")
        to_port = permission.get("ToPort")
        ip_protocol = permission.get("IpProtocol")
        if from_port != port or to_port != port or ip_protocol != "tcp":
            continue

        for ip_range in permission.get("IpRanges", []):
            if ip_range.get("CidrIp") == cidr:
                return True
    return False


def ensure_security_group(ec2_client, group_name: str, port: int, allowed_cidr: str) -> str:
    vpc_id = get_default_vpc_id(ec2_client)
    response = ec2_client.describe_security_groups(
        Filters=[
            {"Name": "group-name", "Values": [group_name]},
            {"Name": "vpc-id", "Values": [vpc_id]},
        ]
    )
    groups = response.get("SecurityGroups", [])

    if groups:
        security_group = groups[0]
        group_id = security_group["GroupId"]
        permissions = security_group.get("IpPermissions", [])
    else:
        create_response = ec2_client.create_security_group(
            GroupName=group_name,
            Description=f"MySQL access for {group_name}",
            VpcId=vpc_id,
        )
        group_id = create_response["GroupId"]
        permissions = []
        print(f"[security-group] Created {group_name} ({group_id}) in VPC {vpc_id}.")

    if not ingress_rule_exists(permissions, allowed_cidr, port):
        try:
            ec2_client.authorize_security_group_ingress(
                GroupId=group_id,
                IpPermissions=[
                    {
                        "IpProtocol": "tcp",
                        "FromPort": port,
                        "ToPort": port,
                        "IpRanges": [
                            {
                                "CidrIp": allowed_cidr,
                                "Description": "Local machine access to MySQL",
                            }
                        ],
                    }
                ],
            )
            print(
                f"[security-group] Authorized TCP/{port} from {allowed_cidr} on {group_id}."
            )
        except ClientError as exc:
            if exc.response["Error"]["Code"] != "InvalidPermission.Duplicate":
                raise

    return group_id


def ensure_security_group_ingress(
    ec2_client, group_id: str, port: int, allowed_cidr: str
) -> None:
    response = ec2_client.describe_security_groups(GroupIds=[group_id])
    groups = response.get("SecurityGroups", [])
    if not groups:
        raise RuntimeError(f"Security group {group_id} was not found.")

    permissions = groups[0].get("IpPermissions", [])
    if ingress_rule_exists(permissions, allowed_cidr, port):
        return

    try:
        ec2_client.authorize_security_group_ingress(
            GroupId=group_id,
            IpPermissions=[
                {
                    "IpProtocol": "tcp",
                    "FromPort": port,
                    "ToPort": port,
                    "IpRanges": [
                        {
                            "CidrIp": allowed_cidr,
                            "Description": "Local machine access to MySQL",
                        }
                    ],
                }
            ],
        )
        print(
            f"[security-group] Authorized TCP/{port} from {allowed_cidr} on {group_id}."
        )
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "InvalidPermission.Duplicate":
            raise


def get_db_instance(rds_client, identifier: str) -> dict[str, object] | None:
    try:
        response = rds_client.describe_db_instances(DBInstanceIdentifier=identifier)
    except rds_client.exceptions.DBInstanceNotFoundFault:
        return None
    return response["DBInstances"][0]


def wait_for_instance(rds_client, identifier: str, timeout_seconds: int) -> None:
    waiter = rds_client.get_waiter("db_instance_available")
    delay = 30
    max_attempts = max(1, math.ceil(timeout_seconds / delay))
    try:
        waiter.wait(
            DBInstanceIdentifier=identifier,
            WaiterConfig={"Delay": delay, "MaxAttempts": max_attempts},
        )
    except WaiterError as exc:
        raise RuntimeError(
            f"Timed out waiting for DB instance {identifier!r} to become available."
        ) from exc


def create_db_instance(
    rds_client,
    *,
    identifier: str,
    db_name: str,
    master_username: str,
    master_password: str,
    instance_class: str,
    allocated_storage: int,
    engine_version: str | None,
    storage_type: str,
    port: int,
    publicly_accessible: bool,
    security_group_ids: list[str],
) -> None:
    params: dict[str, object] = {
        "DBInstanceIdentifier": identifier,
        "DBName": db_name,
        "Engine": "mysql",
        "DBInstanceClass": instance_class,
        "AllocatedStorage": allocated_storage,
        "StorageType": storage_type,
        "MasterUsername": master_username,
        "MasterUserPassword": master_password,
        "Port": port,
        "PubliclyAccessible": publicly_accessible,
        "BackupRetentionPeriod": 0,
        "DeletionProtection": False,
        "AutoMinorVersionUpgrade": True,
        "Tags": [
            {"Key": "Name", "Value": identifier},
            {"Key": "Project", "Value": "classicmodels-lab"},
        ],
    }

    if engine_version:
        params["EngineVersion"] = engine_version

    subnet_group_name = get_env("RDS_DB_SUBNET_GROUP_NAME")
    if subnet_group_name:
        params["DBSubnetGroupName"] = subnet_group_name
    if security_group_ids:
        params["VpcSecurityGroupIds"] = security_group_ids

    rds_client.create_db_instance(**params)


def attach_missing_security_groups(
    rds_client, identifier: str, instance: dict[str, object], desired_group_ids: list[str]
) -> bool:
    if not desired_group_ids:
        return False

    current_group_ids = [
        security_group["VpcSecurityGroupId"]
        for security_group in instance.get("VpcSecurityGroups", [])
    ]
    target_group_ids = sorted(set(current_group_ids) | set(desired_group_ids))

    if target_group_ids == sorted(current_group_ids):
        return False

    rds_client.modify_db_instance(
        DBInstanceIdentifier=identifier,
        VpcSecurityGroupIds=target_group_ids,
        ApplyImmediately=True,
    )
    print(
        "[rds] Updated VPC security groups: "
        + ", ".join(target_group_ids)
    )
    return True


def summarize_instance(instance: dict[str, object]) -> dict[str, object]:
    endpoint = instance.get("Endpoint", {})
    return {
        "identifier": instance["DBInstanceIdentifier"],
        "status": instance["DBInstanceStatus"],
        "endpoint": endpoint.get("Address", ""),
        "port": endpoint.get("Port", ""),
        "engine": instance["Engine"],
        "engine_version": instance["EngineVersion"],
        "publicly_accessible": instance["PubliclyAccessible"],
    }


def main() -> int:
    args = parse_args()
    env_file = resolve_env_path(args.env_file)
    load_env_file(env_file)

    try:
        config = require_env(
            [
                "RDS_DB_INSTANCE_IDENTIFIER",
                "RDS_DB_NAME",
                "RDS_MASTER_USERNAME",
                "RDS_MASTER_PASSWORD",
            ]
        )
        region = get_env("AWS_REGION") or get_env("AWS_DEFAULT_REGION")
        if not region:
            raise ConfigError(
                "Missing AWS region. Set AWS_REGION or AWS_DEFAULT_REGION in .env."
            )
        port = get_int_env("MYSQL_PORT", 3306)
        instance_class = get_env("RDS_INSTANCE_CLASS", "db.t3.micro") or "db.t3.micro"
        allocated_storage = get_int_env("RDS_ALLOCATED_STORAGE", 20)
        engine_version = get_env("RDS_ENGINE_VERSION")
        storage_type = get_env("RDS_STORAGE_TYPE", "gp2") or "gp2"
        publicly_accessible = get_bool_env("RDS_PUBLICLY_ACCESSIBLE", True)
        security_group_ids = parse_security_group_ids(get_env("RDS_VPC_SECURITY_GROUP_IDS"))

        session = boto3.session.Session(region_name=region)
        rds_client = session.client("rds")
        ec2_client = session.client("ec2")

        allowed_cidr = get_env("RDS_ALLOWED_CIDR")
        security_group_name = (
            get_env("RDS_SECURITY_GROUP_NAME")
            or f"{config['RDS_DB_INSTANCE_IDENTIFIER']}-mysql-access"
        )

        if not args.skip_security_group:
            cidr = allowed_cidr or f"{detect_public_ip()}/32"
            if not security_group_ids:
                security_group_id = ensure_security_group(
                    ec2_client=ec2_client,
                    group_name=security_group_name,
                    port=port,
                    allowed_cidr=cidr,
                )
                security_group_ids = [security_group_id]
            else:
                for security_group_id in security_group_ids:
                    ensure_security_group_ingress(
                        ec2_client=ec2_client,
                        group_id=security_group_id,
                        port=port,
                        allowed_cidr=cidr,
                    )
            allowed_cidr = cidr

        instance = get_db_instance(rds_client, config["RDS_DB_INSTANCE_IDENTIFIER"])
        if instance is None:
            engine_label = engine_version or "default AWS-supported MySQL version"
            print(
                f"[rds] Creating DB instance {config['RDS_DB_INSTANCE_IDENTIFIER']} "
                f"({instance_class}, {engine_label})."
            )
            create_db_instance(
                rds_client=rds_client,
                identifier=config["RDS_DB_INSTANCE_IDENTIFIER"],
                db_name=config["RDS_DB_NAME"],
                master_username=config["RDS_MASTER_USERNAME"],
                master_password=config["RDS_MASTER_PASSWORD"],
                instance_class=instance_class,
                allocated_storage=allocated_storage,
                engine_version=engine_version,
                storage_type=storage_type,
                port=port,
                publicly_accessible=publicly_accessible,
                security_group_ids=security_group_ids,
            )
            wait_for_instance(
                rds_client,
                config["RDS_DB_INSTANCE_IDENTIFIER"],
                args.wait_timeout,
            )
            instance = get_db_instance(rds_client, config["RDS_DB_INSTANCE_IDENTIFIER"])
        else:
            print(
                f"[rds] Instance {config['RDS_DB_INSTANCE_IDENTIFIER']} already exists "
                f"with status {instance['DBInstanceStatus']}."
            )
            if instance["DBInstanceStatus"] != "available":
                wait_for_instance(
                    rds_client,
                    config["RDS_DB_INSTANCE_IDENTIFIER"],
                    args.wait_timeout,
                )
                instance = get_db_instance(rds_client, config["RDS_DB_INSTANCE_IDENTIFIER"])

        if instance is None:
            raise RuntimeError("RDS instance could not be described after creation.")

        if attach_missing_security_groups(
            rds_client,
            config["RDS_DB_INSTANCE_IDENTIFIER"],
            instance,
            security_group_ids,
        ):
            wait_for_instance(
                rds_client,
                config["RDS_DB_INSTANCE_IDENTIFIER"],
                args.wait_timeout,
            )
            instance = get_db_instance(rds_client, config["RDS_DB_INSTANCE_IDENTIFIER"])

        if instance is None:
            raise RuntimeError("RDS instance became unavailable after security group update.")

        summary = summarize_instance(instance)
        if not summary["endpoint"]:
            raise RuntimeError("RDS endpoint is not available yet.")

        if not args.no_write_env:
            write_env_updates(
                env_file,
                {
                    "AWS_REGION": region,
                    "AWS_DEFAULT_REGION": region,
                    "RDS_ALLOWED_CIDR": allowed_cidr or "",
                    "RDS_SECURITY_GROUP_NAME": security_group_name,
                    "RDS_VPC_SECURITY_GROUP_IDS": ",".join(security_group_ids),
                    "MYSQL_HOST": summary["endpoint"],
                    "MYSQL_PORT": summary["port"],
                    "MYSQL_USER": config["RDS_MASTER_USERNAME"],
                    "MYSQL_PASSWORD": config["RDS_MASTER_PASSWORD"],
                    "MYSQL_DATABASE": config["RDS_DB_NAME"],
                },
            )
            print(f"[env] Updated {env_file}.")

        print("[rds] Provisioning summary:")
        print(f"  identifier: {summary['identifier']}")
        print(f"  status: {summary['status']}")
        print(f"  endpoint: {summary['endpoint']}")
        print(f"  port: {summary['port']}")
        print(f"  engine: {summary['engine']} {summary['engine_version']}")
        print(f"  publicly_accessible: {summary['publicly_accessible']}")
        if security_group_ids:
            print(f"  security_groups: {', '.join(security_group_ids)}")
        if allowed_cidr:
            print(f"  allowed_cidr: {allowed_cidr}")

        return 0
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code")
        if error_code == "RequestExpired":
            print(
                "[error] AWS request expired. Refresh your temporary AWS credentials "
                "in .env and rerun the provisioning step.",
                file=sys.stderr,
            )
        elif (
            error_code == "InvalidParameterCombination"
            and "Cannot find version" in str(exc)
        ):
            print(
                "[error] The configured RDS engine version is not supported in this "
                "region/account. Remove RDS_ENGINE_VERSION from .env or set it to a "
                "supported value such as 8.0, then rerun provisioning.",
                file=sys.stderr,
            )
        else:
            print(f"[error] {exc}", file=sys.stderr)
        return 1
    except (ConfigError, RuntimeError) as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
