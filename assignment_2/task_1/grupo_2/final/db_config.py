"""
Helper de conexão com o RDS MySQL (classicmodels).

Hierarquia de credenciais (em ordem de prioridade):
  1. AWS Secrets Manager  — se SECRET_ARN estiver definido
  2. Variáveis de ambiente — DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME
  3. Arquivo .env local    — lido automaticamente se existir

Uso:
    from db_config import get_connection

    conn = get_connection()            # transação manual (autocommit=False)
    conn = get_connection(autocommit=True)  # cada statement é commitado

    # Ou via context manager:
    with connect() as conn:
        cur = conn.cursor()
        ...
"""

import json
import os
from contextlib import contextmanager
from pathlib import Path

# ── Leitura do .env (fallback local) ──────────────────────────────────────────

_ENV_CANDIDATES = [
    Path(__file__).resolve().parent / ".env",
    Path(__file__).resolve().parents[3] / "assignment_1" / "task_1" / "rds_connection.env",
    Path(__file__).resolve().parents[4] / "assignment_1" / "task_1" / "rds_connection.env",
]


def _load_env_file() -> dict[str, str]:
    """Lê key=value de um arquivo .env, ignorando comentários e linhas vazias."""
    for candidate in _ENV_CANDIDATES:
        if candidate.is_file():
            env = {}
            for line in candidate.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.strip().strip("'\"")
                if key:
                    env[key] = val
            return env
    return {}


_FILE_ENV = _load_env_file()


def _get(key: str, fallback: str = "") -> str:
    """Retorna variável de ambiente ou valor do .env, com fallback."""
    return os.environ.get(key, _FILE_ENV.get(key, fallback))


# ── Secrets Manager ───────────────────────────────────────────────────────────

def _get_secret_from_aws() -> dict | None:
    """
    Tenta obter credenciais do Secrets Manager.
    Retorna None se SECRET_ARN não estiver definido.
    """
    secret_arn = _get("SECRET_ARN")
    if not secret_arn:
        return None

    import boto3

    region = _get("AWS_REGION", "us-east-1")
    client = boto3.client("secretsmanager", region_name=region)
    payload = client.get_secret_value(SecretId=secret_arn)["SecretString"]
    return json.loads(payload)


# ── Configuração ──────────────────────────────────────────────────────────────

def get_config() -> dict:
    """
    Retorna dicionário de configuração do RDS.

    Prioridade:
      1. Secrets Manager (se SECRET_ARN definido)
      2. Variáveis de ambiente / .env
    """
    secret = _get_secret_from_aws()

    if secret is not None:
        return {
            "host":     secret["host"],
            "port":     int(secret.get("port", 3306)),
            "db":       secret.get("dbname", "classicmodels"),
            "user":     secret["username"],
            "password": secret["password"],
            "source":   "secrets_manager",
        }

    return {
        "host":     _get("DB_HOST", _get("RDS_HOST")),
        "port":     int(_get("DB_PORT", _get("RDS_PORT", "3306"))),
        "db":       _get("DB_NAME", _get("RDS_DB", "classicmodels")),
        "user":     _get("DB_USER", _get("RDS_USER", "admin")),
        "password": _get("DB_PASSWORD", _get("RDS_PASSWORD")),
        "source":   "env",
    }


def get_connection(autocommit: bool = False):
    """
    Retorna uma conexão pymysql com o banco classicmodels.

    Args:
        autocommit: se True, cada statement é commitado automaticamente.
                    Para transações explícitas, use False (default).
    """
    import pymysql

    cfg = get_config()

    if not cfg["host"]:
        raise RuntimeError(
            "Host do banco não definido. Configure:\n"
            "  • SECRET_ARN (para Secrets Manager), ou\n"
            "  • DB_HOST via variável de ambiente, ou\n"
            "  • Arquivo .env na raiz do projeto."
        )

    return pymysql.connect(
        host=cfg["host"],
        port=cfg["port"],
        user=cfg["user"],
        password=cfg["password"],
        database=cfg["db"],
        charset="utf8mb4",
        connect_timeout=15,
        autocommit=autocommit,
    )


@contextmanager
def connect(autocommit: bool = False):
    """
    Context manager para conexão com o banco.

    Uso:
        with connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT 1")
    """
    conn = get_connection(autocommit=autocommit)
    try:
        yield conn
    finally:
        conn.close()
