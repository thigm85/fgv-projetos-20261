"""
Helper de conexão compartilhado pelos scripts da Task 1 (Assignment 2).

Reusa o padrão estabelecido no Assignment 1:
  - Senha via .env (RDS_ADMIN_PASSWORD), nunca hardcoded.
  - Endpoint/porta/usuário via pipeline_info.json (gerado por terraform apply).
  - Conexão pymysql com retry e backoff exponencial.

Espera-se que .env e pipeline_info.json estejam neste mesmo diretório (scripts/).
"""
import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
import pymysql

BASE_DIR = Path(__file__).parent

MAX_RETRIES = 5
CONNECT_TIMEOUT = 10
DB_NAME = "classicmodels"


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        print(f"[ERRO] Variável de ambiente obrigatória não definida: {name}")
        print("       Defina-a no arquivo .env em scripts/ (use .env.example como base).")
        sys.exit(1)
    return value


def load_config() -> dict:
    """Carrega credenciais (.env) e metadados de conexão (pipeline_info.json)."""
    load_dotenv(BASE_DIR / ".env")

    info_path = BASE_DIR / "pipeline_info.json"
    if not info_path.exists():
        print(f"[ERRO] pipeline_info.json não encontrado em {info_path}.")
        print("       Copie-o da pasta do Assignment 1 (terraform output).")
        sys.exit(1)

    info = json.loads(info_path.read_text())
    return {
        "host": info["rds_endpoint"],
        "port": int(info["rds_port"]),
        "user": info["rds_admin_user"],
        "password": require_env("RDS_ADMIN_PASSWORD"),
        "database": info.get("rds_db_name", DB_NAME),
    }


def connect_with_retry(cfg: dict, max_retries: int = MAX_RETRIES) -> pymysql.connections.Connection:
    """Conecta ao RDS com retry e backoff exponencial (2, 4, 8, 16s)."""
    for attempt in range(1, max_retries + 1):
        try:
            print(f"[{attempt}/{max_retries}] Conectando a {cfg['host']}:{cfg['port']}/{cfg['database']}...")
            conn = pymysql.connect(
                host=cfg["host"],
                port=cfg["port"],
                user=cfg["user"],
                password=cfg["password"],
                database=cfg["database"],
                connect_timeout=CONNECT_TIMEOUT,
            )
            print("  Conexão estabelecida.")
            return conn
        except Exception as exc:
            if "Unknown database" in str(exc):
                print(f"[ERRO] O banco '{cfg['database']}' não existe. Rode a carga do Assignment 1 primeiro.")
                sys.exit(1)
            if attempt == max_retries:
                print(f"[ERRO] Falha após {max_retries} tentativas: {exc}")
                raise
            wait = 2 ** attempt
            print(f"  Falha: {exc}. Aguardando {wait}s...")
            time.sleep(wait)
