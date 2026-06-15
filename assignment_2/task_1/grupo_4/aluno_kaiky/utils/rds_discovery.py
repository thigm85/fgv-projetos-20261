"""Fetch RDS endpoint from AWS and write DB_HOST / DB_PORT to .env when missing."""

from __future__ import annotations

import os
from pathlib import Path

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from dotenv import set_key

DEFAULT_RDS_INSTANCE_IDENTIFIER = "classicmodels-mysql-g4"
DEFAULT_AWS_REGION = "us-east-1"


def _fetch_endpoint() -> tuple[str, int]:
    """DescribeDBInstances using RDS_DB_INSTANCE_IDENTIFIER and AWS_REGION from the environment."""
    ident = os.getenv("RDS_DB_INSTANCE_IDENTIFIER", DEFAULT_RDS_INSTANCE_IDENTIFIER).strip()
    region = os.getenv("AWS_REGION", DEFAULT_AWS_REGION).strip()

    try:
        response = boto3.client("rds", region_name=region).describe_db_instances(
            DBInstanceIdentifier=ident
        )
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code == "DBInstanceNotFound":
            raise RuntimeError(
                f"RDS instance '{ident}' not found in {region}. "
                "Set RDS_DB_INSTANCE_IDENTIFIER and AWS_REGION in .env."
            ) from exc
        raise RuntimeError(f"AWS error describing RDS '{ident}': {exc}") from exc
    except BotoCoreError as exc:
        raise RuntimeError(f"AWS credentials or network error: {exc}") from exc

    instance = response["DBInstances"][0]
    endpoint = instance.get("Endpoint") or {}
    host = endpoint.get("Address")
    if not host:
        raise RuntimeError(
            f"RDS '{ident}' has no endpoint yet (status={instance.get('DBInstanceStatus')})."
        )
    port = int(endpoint.get("Port") or instance.get("DbInstancePort") or 3306)
    return host, port


def fill_db_host_if_missing(env_path: Path) -> None:
    """If DB_HOST is empty, resolve it via AWS and persist to the .env file."""
    if os.getenv("DB_HOST", "").strip():
        return

    if not env_path.is_file():
        example = env_path.parent / ".env.example"
        if example.is_file():
            env_path.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
        else:
            raise FileNotFoundError(f"Missing {env_path}. Copy .env.example to .env first.")

    host, port = _fetch_endpoint()
    set_key(str(env_path), "DB_HOST", host)
    set_key(str(env_path), "DB_PORT", str(port))
    os.environ["DB_HOST"] = host
    os.environ["DB_PORT"] = str(port)
    print(f"[RDS] DB_HOST set to {host} (saved in {env_path.name})")
