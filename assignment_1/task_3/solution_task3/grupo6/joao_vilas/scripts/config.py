from __future__ import annotations

import json
import logging
import os
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv
except ImportError:  
    load_dotenv = None

import boto3


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TERRAFORM_DIR = PROJECT_ROOT / "terraform"

logger = logging.getLogger(__name__)

if load_dotenv is not None:
    load_dotenv(PROJECT_ROOT / ".env", override=False)


@dataclass(frozen=True)
class AppConfig:
    aws_region: str
    project_prefix: str
    db_secret_id: str
    glue_database: str
    athena_workgroup: str
    athena_output_s3: str
    etl_bucket: str
    sql_path: Path
    connect_retries: int
    connect_delay_seconds: int


@dataclass(frozen=True)
class DbCredentials:
    username: str
    password: str
    host: str
    port: int
    dbname: str


def _try_terraform_outputs() -> dict[str, Any]:
    """Le os outputs do Terraform se o estado estiver acessivel localmente."""

    if not (TERRAFORM_DIR / ".terraform").exists():
        return {}

    try:
        result = subprocess.run(
            ["terraform", f"-chdir={TERRAFORM_DIR}", "output", "-json"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        logger.debug("Nao foi possivel ler outputs do Terraform: %s", exc)
        return {}

    try:
        raw = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {}

    return {key: value.get("value") for key, value in raw.items()}


@lru_cache(maxsize=1)
def load_config() -> AppConfig:
    tf_outputs = _try_terraform_outputs()

    def pick(env_key: str, tf_key: str, default: str | None = None) -> str:
        value = os.getenv(env_key) or tf_outputs.get(tf_key) or default
        if not value:
            raise RuntimeError(
                f"Configuracao ausente: defina {env_key} no ambiente ou rode "
                "`terraform output` no diretorio terraform/."
            )
        return str(value)

    sql_path = Path(os.getenv("MYSQL_SQL_PATH", "data/mysqlsampledatabase.sql"))
    if not sql_path.is_absolute():
        sql_path = PROJECT_ROOT / sql_path

    return AppConfig(
        aws_region=pick("AWS_REGION", "aws_region", "us-east-1"),
        project_prefix=os.getenv("PROJECT_PREFIX", "joao-vilas-task3"),
        db_secret_id=pick("DB_SECRET_ID", "db_secret_id"),
        glue_database=pick("GLUE_DATABASE", "glue_database"),
        athena_workgroup=pick("ATHENA_WORKGROUP", "athena_workgroup"),
        athena_output_s3=pick("ATHENA_OUTPUT_S3", "athena_output_s3"),
        etl_bucket=pick("ETL_BUCKET", "etl_bucket_name"),
        sql_path=sql_path,
        connect_retries=int(os.getenv("MYSQL_CONNECT_RETRIES", "10")),
        connect_delay_seconds=int(os.getenv("MYSQL_CONNECT_DELAY_SECONDS", "10")),
    )


@lru_cache(maxsize=1)
def load_db_credentials() -> DbCredentials:

    config = load_config()

    client = boto3.client("secretsmanager", region_name=config.aws_region)
    response = client.get_secret_value(SecretId=config.db_secret_id)

    payload = json.loads(response["SecretString"])

    return DbCredentials(
        username=payload["username"],
        password=payload["password"],
        host=payload["host"],
        port=int(payload["port"]),
        dbname=payload["dbname"],
    )
