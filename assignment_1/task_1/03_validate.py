#!/usr/bin/env python3
"""Valida a carga do classicmodels no MySQL (RDS)."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Iterable

import pymysql
from botocore.exceptions import ClientError
from dotenv import load_dotenv
from aws_net import authorize_mysql_ingress, format_aws_error, resolve_rds_host

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

EXPECTED_TABLES = {
    "customers",
    "employees",
    "offices",
    "orderdetails",
    "orders",
    "payments",
    "productlines",
    "products",
}


def env_any(names: Iterable[str], default: str | None = None, required: bool = False) -> str:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    if required and not default:
        raise RuntimeError(f"Variável obrigatória ausente: {', '.join(names)}")
    return default or ""


def resolve_host(region: str, identifier: str | None, current_host: str | None) -> str:
    if identifier:
        host, _ = resolve_rds_host(region, identifier)
        if host:
            return host
        raise RuntimeError(
            f"Endpoint do RDS ainda indisponível para '{identifier}'. "
            "Defina RDS_WAIT=true no 01_instance.py e execute novamente."
        )
    if current_host:
        return current_host
    raise RuntimeError("Defina MYSQL_HOST ou RDS_DB_INSTANCE_IDENTIFIER/DB_INSTANCE_ID")


def quote_ident(name: str) -> str:
    return "`" + name.replace("`", "``") + "`"


def main() -> int:
    logger.info("Passo 1/6 - Carregando variáveis de ambiente")
    load_dotenv(dotenv_path=Path(__file__).with_name(".env"), override=True)

    logger.info("Passo 2/6 - Resolvendo conexão MySQL")
    region = env_any(["AWS_REGION", "AWS_DEFAULT_REGION"], "us-east-1")
    identifier = env_any(["RDS_DB_INSTANCE_IDENTIFIER", "DB_INSTANCE_ID"], "") or None
    port = int(env_any(["MYSQL_PORT", "DB_PORT", "RDS_PORT"], "3306"))
    user = env_any(["MYSQL_USER", "DB_USER", "RDS_MASTER_USERNAME"], "admin")
    password = env_any(["MYSQL_PASSWORD", "DB_PASSWORD", "RDS_MASTER_PASSWORD"], required=True)
    database = env_any(["MYSQL_DATABASE", "DB_NAME", "RDS_DB_NAME"], "classicmodels")

    logger.info("Passo 3/6 - Aplicando regra de rede via detect_public_ip")
    if identifier:
        try:
            authorize_mysql_ingress(region, port, identifier=identifier, logger=logger)
        except Exception as exc:
            logger.warning("Falha ao autorizar ingress automático: %s", exc)
    else:
        logger.warning("Sem RDS identifier; pulando detect_public_ip para SG")

    try:
        host = resolve_host(region, identifier, os.getenv("MYSQL_HOST"))
    except ClientError as exc:
        logger.error("%s", format_aws_error(exc))
        return 1
    except RuntimeError as exc:
        logger.error("%s", exc)
        return 1

    logger.info("Passo 4/6 - Conectando ao banco %s em %s:%s", database, host, port)
    conn = pymysql.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
        charset="utf8mb4",
        autocommit=True,
        cursorclass=pymysql.cursors.DictCursor,
    )

    try:
        with conn.cursor() as cursor:
            logger.info("Passo 5/6 - Validando tabelas esperadas")
            cursor.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = %s
                """,
                (database,),
            )
            rows = cursor.fetchall()
            existing = {row.get("table_name") or row.get("TABLE_NAME") for row in rows}
            existing = {name for name in existing if name}

            missing = EXPECTED_TABLES - existing
            extras = existing - EXPECTED_TABLES

            logger.info("Tabelas encontradas: %s", ", ".join(sorted(existing)))
            if missing:
                logger.error("Tabelas faltando: %s", ", ".join(sorted(missing)))
                return 1
            if extras:
                logger.info("Tabelas extras: %s", ", ".join(sorted(extras)))

            for table in sorted(EXPECTED_TABLES):
                cursor.execute(f"SELECT COUNT(*) AS total FROM {quote_ident(table)}")
                total = cursor.fetchone()["total"]
                logger.info("%s: %s", table, total)

            logger.info("Passo 6/6 - Validação concluída com sucesso")
            return 0
    except Exception as exc:
        logger.error("Falha na validação: %s", exc)
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
