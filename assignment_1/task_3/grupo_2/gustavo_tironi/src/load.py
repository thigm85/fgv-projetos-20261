"""
Carga do banco classicmodels no RDS MySQL.

Estratégia:
  - lê credenciais do Secrets Manager
  - retry de conexão (RDS recém-provisionado pode oscilar)
  - executa o SQL inteiro de uma vez via cmd_query_iter (multi-statement)
  - transação explícita: commit no sucesso, rollback no erro
  - logs estruturados por etapa

Exit code: 0 = sucesso, 1 = falha.
"""

import json
import logging
import os
import sys
import time
from pathlib import Path

import boto3
import mysql.connector
from mysql.connector import Error as MySQLError

import envlocal

envlocal.load()

# ── config ───────────────────────────────────────────────────────────────────
SECRET_ARN = os.environ["SECRET_ARN"]
REGION = os.environ.get("AWS_REGION", "us-east-1")
SQL_FILE = Path(__file__).resolve().parents[3] / "data" / "mysqlsampledatabase.sql"

CONNECT_RETRIES = 5
CONNECT_DELAY_SECONDS = 10

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("load")


def get_secret() -> dict:
    log.info("Passo 1/5 — Buscando credenciais no Secrets Manager")
    client = boto3.client("secretsmanager", region_name=REGION)
    payload = client.get_secret_value(SecretId=SECRET_ARN)["SecretString"]
    return json.loads(payload)


def connect_with_retry(secret: dict):
    log.info("Passo 2/5 — Conectando ao RDS (%s)", secret["host"])
    last_exc = None
    for attempt in range(1, CONNECT_RETRIES + 1):
        try:
            conn = mysql.connector.connect(
                host=secret["host"],
                user=secret["username"],
                password=secret["password"],
                port=int(secret["port"]),
                use_pure=True,
                autocommit=False,
                connection_timeout=10,
            )
            log.info("  conectado (tentativa %d/%d)", attempt, CONNECT_RETRIES)
            return conn
        except MySQLError as exc:
            last_exc = exc
            log.warning(
                "  tentativa %d/%d falhou: %s", attempt, CONNECT_RETRIES, exc
            )
            if attempt < CONNECT_RETRIES:
                time.sleep(CONNECT_DELAY_SECONDS)
    raise RuntimeError(f"Falha ao conectar após {CONNECT_RETRIES} tentativas: {last_exc}")


def read_sql() -> str:
    log.info("Passo 3/5 — Lendo script SQL (%s)", SQL_FILE)
    if not SQL_FILE.exists():
        raise FileNotFoundError(f"Script SQL não encontrado: {SQL_FILE}")
    sql = SQL_FILE.read_text(encoding="utf-8", errors="replace")
    log.info("  script carregado (%.1f KB)", len(sql) / 1024)
    return sql


def run_load(conn, sql: str) -> None:
    log.info("Passo 4/5 — Executando carga (multi-statement, single shot)")
    started = time.time()
    try:
        for result in conn.cmd_query_iter(sql):
            if "columns" in result:
                conn.get_rows()
        conn.commit()
        elapsed = time.time() - started
        log.info("  commit ok (%.1fs)", elapsed)
    except Exception as exc:
        conn.rollback()
        log.exception("  rollback aplicado: %s", exc)
        raise


def main() -> int:
    if os.environ.get("DRY_RUN") == "1":
        log.info("DRY_RUN=1 → sem execução. Plano:")
        log.info("  1) ler secret %s", SECRET_ARN)
        log.info("  2) conectar (retry %dx)", CONNECT_RETRIES)
        log.info("  3) ler %s", SQL_FILE)
        log.info("  4) executar SQL em transação")
        log.info("  5) commit/rollback + close")
        return 0

    conn = None
    try:
        secret = get_secret()
        sql = read_sql()
        conn = connect_with_retry(secret)
        run_load(conn, sql)
        log.info("Passo 5/5 — classicmodels carregado com sucesso")
        return 0
    except Exception as exc:
        log.error("Carga falhou: %s", exc)
        return 1
    finally:
        if conn is not None and conn.is_connected():
            conn.close()
            log.info("  conexão fechada")


if __name__ == "__main__":
    sys.exit(main())
