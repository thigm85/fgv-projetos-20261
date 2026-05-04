#!/usr/bin/env python3
"""Utilitários de rede para acesso ao RDS via IP público atual."""

from __future__ import annotations

import ipaddress
import logging
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

import boto3
from botocore.exceptions import ClientError


def aws_error_code(exc: ClientError) -> str:
    return exc.response.get("Error", {}).get("Code", "Unknown")


def is_expired_token(exc: ClientError) -> bool:
    return aws_error_code(exc) in {"ExpiredToken", "ExpiredTokenException", "RequestExpired"}


def format_aws_error(exc: ClientError) -> str:
    if is_expired_token(exc):
        return (
            "Token AWS expirado. Gere credenciais novas (STS), atualize "
            "AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY/AWS_SESSION_TOKEN e tente novamente."
        )

    code = aws_error_code(exc)
    msg = exc.response.get("Error", {}).get("Message", str(exc))
    return f"Falha AWS ({code}): {msg}"


def detect_public_ip(timeout: int = 5) -> str:
    endpoints = (
        "https://checkip.amazonaws.com",
        "https://api.ipify.org",
        "https://ifconfig.me/ip",
    )
    errors: list[str] = []

    for endpoint in endpoints:
        try:
            with urlopen(endpoint, timeout=timeout) as response:
                raw = response.read().decode("utf-8", errors="ignore").strip()
            ip = raw.splitlines()[0].strip()
            ipaddress.ip_address(ip)
            return ip
        except (URLError, ValueError, IndexError) as exc:
            errors.append(f"{endpoint}: {exc}")

    raise RuntimeError(f"Falha ao detectar IP público ({'; '.join(errors)})")


def describe_instance(region: str, identifier: str) -> dict[str, Any]:
    rds = boto3.client("rds", region_name=region)
    response = rds.describe_db_instances(DBInstanceIdentifier=identifier)
    return response["DBInstances"][0]


def resolve_rds_host(region: str, identifier: str) -> tuple[str | None, dict[str, Any]]:
    instance = describe_instance(region, identifier)
    endpoint = instance.get("Endpoint", {})
    host = endpoint.get("Address")
    return host, instance


def authorize_mysql_ingress(
    region: str,
    port: int,
    *,
    identifier: str | None = None,
    instance: dict[str, Any] | None = None,
    logger: logging.Logger | None = None,
    description: str = "assignment_1/task_1 detect_public_ip",
) -> str | None:
    log = logger or logging.getLogger(__name__)

    resolved_instance = instance
    if resolved_instance is None:
        if not identifier:
            raise ValueError("identifier ou instance é obrigatório")
        resolved_instance = describe_instance(region, identifier)

    sg_ids = [
        item.get("VpcSecurityGroupId")
        for item in resolved_instance.get("VpcSecurityGroups", [])
        if item.get("VpcSecurityGroupId")
    ]
    if not sg_ids:
        log.warning("Sem security group no RDS; pulando autorização automática")
        return None

    public_ip = detect_public_ip()
    cidr = f"{public_ip}/32"

    ec2 = boto3.client("ec2", region_name=region)
    for sg_id in sg_ids:
        try:
            ec2.authorize_security_group_ingress(
                GroupId=sg_id,
                IpPermissions=[
                    {
                        "IpProtocol": "tcp",
                        "FromPort": port,
                        "ToPort": port,
                        "IpRanges": [{"CidrIp": cidr, "Description": description}],
                    }
                ],
            )
            log.info("Ingress liberado: %s porta %s no SG %s", cidr, port, sg_id)
        except ClientError as exc:
            if aws_error_code(exc) == "InvalidPermission.Duplicate":
                log.info("Ingress já existia: %s porta %s no SG %s", cidr, port, sg_id)
            else:
                raise

    return cidr
