#!/usr/bin/env python3
from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

from config_utils import configure_aws_env, load_env_config, section


ROOT = Path(__file__).resolve().parent
CONFIG_DIR = ROOT / "config"
ENDPOINT_FILE = CONFIG_DIR / "db_endpoint.json"


def load_config() -> dict:
    config = load_env_config()
    configure_aws_env(config)
    rds = section(config, "rds")
    aws = section(config, "default")
    rds["region"] = aws.get("region", "us-east-1")
    return rds


def detect_public_cidr() -> str:
    with urllib.request.urlopen("https://checkip.amazonaws.com", timeout=10) as response:
        ip = response.read().decode("utf-8").strip()
    return f"{ip}/32"


def default_vpc_id(ec2) -> str:
    response = ec2.describe_vpcs(Filters=[{"Name": "isDefault", "Values": ["true"]}])
    vpcs = response.get("Vpcs", [])
    if not vpcs:
        raise RuntimeError("Default VPC not found in this AWS account/region.")
    return vpcs[0]["VpcId"]


def ensure_security_group(ec2, name: str, port: int) -> str:
    vpc_id = default_vpc_id(ec2)
    groups = ec2.describe_security_groups(
        Filters=[
            {"Name": "group-name", "Values": [name]},
            {"Name": "vpc-id", "Values": [vpc_id]},
        ]
    ).get("SecurityGroups", [])

    if groups:
        sg_id = groups[0]["GroupId"]
        permissions = groups[0].get("IpPermissions", [])
    else:
        sg_id = ec2.create_security_group(
            GroupName=name,
            Description="Grupo 5 MySQL source access",
            VpcId=vpc_id,
        )["GroupId"]
        permissions = []
        print(f"[sg] Created {name}: {sg_id}")

    cidr = detect_public_cidr()
    already_exists = any(
        permission.get("IpProtocol") == "tcp"
        and permission.get("FromPort") == port
        and permission.get("ToPort") == port
        and any(item.get("CidrIp") == cidr for item in permission.get("IpRanges", []))
        for permission in permissions
    )
    if already_exists:
        print(f"[sg] Ingress already exists for {cidr}:{port}")
        return sg_id

    try:
        ec2.authorize_security_group_ingress(
            GroupId=sg_id,
            IpPermissions=[
                {
                    "IpProtocol": "tcp",
                    "FromPort": port,
                    "ToPort": port,
                    "IpRanges": [{"CidrIp": cidr, "Description": "Current local IP"}],
                }
            ],
        )
        print(f"[sg] Authorized {cidr}:{port}")
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") != "InvalidPermission.Duplicate":
            raise
    return sg_id


def describe_rds(rds, identifier: str) -> dict | None:
    try:
        return rds.describe_db_instances(DBInstanceIdentifier=identifier)["DBInstances"][0]
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") in {
            "DBInstanceNotFound",
            "DBInstanceNotFoundFault",
        }:
            return None
        raise


def wait_available(rds, identifier: str) -> dict:
    print(f"[rds] Waiting for {identifier} to become available")
    rds.get_waiter("db_instance_available").wait(
        DBInstanceIdentifier=identifier,
        WaiterConfig={"Delay": 30, "MaxAttempts": 80},
    )
    instance = describe_rds(rds, identifier)
    if not instance:
        raise RuntimeError(f"RDS instance {identifier} disappeared after wait.")
    return instance


def main() -> int:
    cfg = load_config()
    region = cfg.get("region", "us-east-1")
    identifier = cfg["db_instance_id"]
    port = int(cfg.get("db_port", 3306))

    session = boto3.session.Session(region_name=region)
    ec2 = session.client("ec2")
    rds = session.client("rds")

    sg_id = ensure_security_group(ec2, f"{identifier}-mysql-access", port)
    instance = describe_rds(rds, identifier)

    if instance:
        print(f"[rds] Reusing {identifier} with status {instance['DBInstanceStatus']}")
        if instance["DBInstanceStatus"] != "available":
            instance = wait_available(rds, identifier)
    else:
        print(f"[rds] Creating {identifier}")
        rds.create_db_instance(
            DBInstanceIdentifier=identifier,
            DBName=cfg.get("db_name", "classicmodels"),
            AllocatedStorage=int(cfg.get("allocated_storage", 20)),
            DBInstanceClass=cfg.get("instance_class", "db.t3.micro"),
            Engine="mysql",
            MasterUsername=cfg["db_user"],
            MasterUserPassword=cfg["db_password"],
            PubliclyAccessible=True,
            VpcSecurityGroupIds=[sg_id],
            BackupRetentionPeriod=0,
            DeletionProtection=False,
            AutoMinorVersionUpgrade=True,
            Tags=[
                {"Key": "Project", "Value": "assignment-1-task-2"},
                {"Key": "Group", "Value": "grupo-5"},
            ],
        )
        instance = wait_available(rds, identifier)

    endpoint = instance["Endpoint"]["Address"]
    endpoint_payload = {
        "host": endpoint,
        "port": instance["Endpoint"].get("Port", port),
        "database": cfg.get("db_name", "classicmodels"),
        "security_group_id": sg_id,
    }
    ENDPOINT_FILE.write_text(json.dumps(endpoint_payload, indent=2), encoding="utf-8")
    print(f"[rds] Endpoint saved to {ENDPOINT_FILE}")
    print(json.dumps(endpoint_payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
