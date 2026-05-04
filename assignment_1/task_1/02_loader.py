#!/usr/bin/env python3
"""Carrega o dataset classicmodels no MySQL (RDS) com fallback de endpoint via AWS."""

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


def env_any(names: Iterable[str], default: str | None = None, required: bool = False) -> str:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    if required and not default:
        raise RuntimeError(f"Variável obrigatória ausente: {', '.join(names)}")
    return default or ""


def resolve_sql_file() -> Path:
    explicit = os.getenv("MYSQL_SQL_FILE")
    if explicit:
        return Path(explicit)

    candidates = [
        Path("assignment_1/task_1/data/mysqlsampledatabase.sql"),
        Path("task_1/data/mysqlsampledatabase.sql"),
        Path("data/mysqlsampledatabase.sql"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


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


def split_sql_statements(script: str) -> list[str]:
    statements: list[str] = []
    buf: list[str] = []
    in_single = False
    in_double = False
    in_backtick = False
    escaped = False

    for ch in script:
        buf.append(ch)

        if escaped:
            escaped = False
            continue
        if ch == "\\":
            escaped = True
            continue
        if not in_double and not in_backtick and ch == "'":
            in_single = not in_single
            continue
        if not in_single and not in_backtick and ch == '"':
            in_double = not in_double
            continue
        if not in_single and not in_double and ch == "`":
            in_backtick = not in_backtick
            continue
        if ch == ";" and not in_single and not in_double and not in_backtick:
            stmt = "".join(buf).strip()
            if stmt:
                statements.append(stmt)
            buf = []

    tail = "".join(buf).strip()
    if tail:
        statements.append(tail)

    return statements


def main() -> int:
    logger.info("Passo 1/7 - Carregando variáveis de ambiente")
    load_dotenv(dotenv_path=Path(__file__).with_name(".env"), override=True)

    logger.info("Passo 2/7 - Resolvendo conexão e arquivo SQL")
    region = env_any(["AWS_REGION", "AWS_DEFAULT_REGION"], "us-east-1")
    identifier = env_any(["RDS_DB_INSTANCE_IDENTIFIER", "DB_INSTANCE_ID"], "") or None
    port = int(env_any(["MYSQL_PORT", "DB_PORT", "RDS_PORT"], "3306"))
    user = env_any(["MYSQL_USER", "DB_USER", "RDS_MASTER_USERNAME"], "admin")
    password = env_any(["MYSQL_PASSWORD", "DB_PASSWORD", "RDS_MASTER_PASSWORD"], required=True)
    database = env_any(["MYSQL_DATABASE", "DB_NAME", "RDS_DB_NAME"], "classicmodels")

    logger.info("Passo 3/7 - Aplicando regra de rede via detect_public_ip")
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

    sql_file = resolve_sql_file()
    if not sql_file.exists():
        logger.error("Arquivo SQL não encontrado: %s", sql_file)
        return 1

    script = sql_file.read_text(encoding="utf-8")
    statements = split_sql_statements(script)
    if not statements:
        logger.error("Nenhum statement SQL encontrado no arquivo")
        return 1

    logger.info("Passo 4/7 - Abrindo conexão MySQL em %s:%s", host, port)
    conn = pymysql.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        charset="utf8mb4",
        autocommit=False,
        cursorclass=pymysql.cursors.Cursor,
    )

    safe_database = quote_ident(database)

    try:
        logger.info("Passo 5/7 - Criando/selecionando database %s", database)
        with conn.cursor() as cursor:
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS {safe_database}")
            cursor.execute(f"USE {safe_database}")

            logger.info("Passo 6/7 - Executando %s statements SQL", len(statements))
            total = len(statements)
            for i, stmt in enumerate(statements, start=1):
                cursor.execute(stmt)
                if i % 100 == 0 or i == total:
                    logger.info("Executados %s/%s statements", i, total)

        conn.commit()
    except Exception as exc:
        conn.rollback()
        logger.error("Falha na carga: %s", exc)
        return 1
    finally:
        conn.close()

    logger.info("Passo 7/7 - Carga concluída com sucesso")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
