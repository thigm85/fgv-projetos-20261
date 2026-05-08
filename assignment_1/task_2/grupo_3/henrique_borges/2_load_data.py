"""
Carrega o banco classicmodels no RDS provisionado via Terraform.
Lê credenciais do .env e endpoint do pipeline_info.json (gerado por terraform apply).
"""
import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
import pymysql
import pymysql.constants.CLIENT

BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")

# --- Configuração ---

def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        print(f"[ERRO] Variável de ambiente obrigatória não definida: {name}")
        sys.exit(1)
    return value

RDS_ADMIN_PASSWORD = require_env("RDS_ADMIN_PASSWORD")

info_path = BASE_DIR / "pipeline_info.json"
if not info_path.exists():
    print("[ERRO] pipeline_info.json não encontrado. Execute 'terraform apply' primeiro.")
    sys.exit(1)

info = json.loads(info_path.read_text())
RDS_ENDPOINT   = info["rds_endpoint"]
RDS_PORT       = int(info["rds_port"])
RDS_ADMIN_USER = info["rds_admin_user"]

SQL_PATH = BASE_DIR.parents[2] / "task_1" / "data" / "mysqlsampledatabase.sql"
if not SQL_PATH.exists():
    print(f"[ERRO] Arquivo SQL não encontrado: {SQL_PATH}")
    sys.exit(1)

MAX_RETRIES  = 5
CONNECT_TIMEOUT = 10


# --- Conexão com retry e backoff exponencial ---

def connect_with_retry() -> pymysql.connections.Connection:
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            print(f"[{attempt}/{MAX_RETRIES}] Conectando a {RDS_ENDPOINT}:{RDS_PORT}...")
            conn = pymysql.connect(
                host=RDS_ENDPOINT,
                port=RDS_PORT,
                user=RDS_ADMIN_USER,
                password=RDS_ADMIN_PASSWORD,
                connect_timeout=CONNECT_TIMEOUT,
                client_flag=pymysql.constants.CLIENT.MULTI_STATEMENTS,
            )
            print("  Conexão estabelecida.")
            return conn
        except Exception as exc:
            if attempt == MAX_RETRIES:
                print(f"[ERRO] Falha após {MAX_RETRIES} tentativas: {exc}")
                raise
            wait = 2 ** attempt  # 2, 4, 8, 16 segundos
            print(f"  Falha: {exc}. Aguardando {wait}s antes de tentar novamente...")
            time.sleep(wait)


# --- Carga com transação ---

def load_sql(conn: pymysql.connections.Connection) -> None:
    print(f"Lendo SQL de {SQL_PATH}...")
    sql = SQL_PATH.read_text(encoding="utf-8")
    print(f"  {len(sql):,} bytes lidos.")

    print("Executando SQL no RDS...")
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            result_sets = 0
            while cur.nextset():
                result_sets += 1
        conn.commit()
        print(f"  Carga concluída e commitada ({result_sets} result sets processados).")
    except Exception as exc:
        conn.rollback()
        raise RuntimeError(
            f"Falha na execução do SQL — rollback realizado.\n"
            f"Causa: {exc}"
        ) from exc
    finally:
        conn.close()
        print("  Conexão encerrada.")


# --- Execução principal ---

def main(dry_run: bool = False) -> int:
    print("=" * 50)
    if dry_run:
        print("[DRY-RUN] Nenhuma alteração será feita no banco.")
    print("Passo 1/3 — Validando configuração")
    print(f"  Endpoint  : {RDS_ENDPOINT}:{RDS_PORT}")
    print(f"  Usuário   : {RDS_ADMIN_USER}")
    print(f"  SQL source: {SQL_PATH.name} ({SQL_PATH.stat().st_size:,} bytes)")

    if dry_run:
        print("\n[DRY-RUN] Passo 2/3 — Testando conectividade (sem executar SQL)")
        conn = connect_with_retry()
        conn.close()
        print("  Conexão OK. Encerrada sem carregar dados.")
        print("\n[DRY-RUN] Passo 3/3 — SQL seria executado no banco classicmodels")
        print("  Nenhuma carga realizada.")
        print("=" * 50)
        return 0

    print("\nPasso 2/3 — Conectando ao RDS")
    conn = connect_with_retry()

    print("\nPasso 3/3 — Carregando banco classicmodels")
    load_sql(conn)

    print("\nCarga finalizada com sucesso.")
    print("=" * 50)
    return 0


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    sys.exit(main(dry_run=dry_run))
