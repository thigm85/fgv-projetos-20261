"""
Cria o banco classicmodels e carrega o arquivo SQL de exemplo.
Busca dinamicamente o endpoint do RDS através dos outputs do Terraform.
"""

import json
import sys
import os
import time
import subprocess
import mysql.connector
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------
# CONFIGURAÇÕES
# ---------------------------------------------
DB_NAME = "classicmodels"

# Caminho absoluto para garantir que sempre acha o arquivo independente de onde o script for rodado
base_dir = os.path.dirname(__file__)
default_sql_path = os.path.abspath(os.path.join(base_dir, "..", "..", "..", "data", "mysqlsampledatabase.sql"))
LOCAL_SQL = os.getenv("SQL_FILE", default_sql_path)

# parâmetros de retry de conexão
CONNECT_RETRIES = 5
CONNECT_DELAY_S = 10   # segundos entre tentativas

# --- Utilitários -----------------------------

def get_terraform_outputs() -> dict:
    """Extrai os outputs do terraform na pasta ../terraform"""
    tf_dir = os.path.join(os.path.dirname(__file__), "..", "terraform")
    try:
        res = subprocess.run(["terraform", "output", "-json"], cwd=tf_dir, capture_output=True, text=True, check=True)
        return json.loads(res.stdout)
    except subprocess.CalledProcessError as e:
        sys.exit(f"X Erro ao rodar terraform output: {e.stderr}\nVocê já executou terraform apply?")

def get_credentials() -> dict:
    outputs = get_terraform_outputs()
    host = outputs.get("rds_endpoint", {}).get("value")
    port = outputs.get("rds_port", {}).get("value", 3306)
    
    # Credenciais do .env (preferencialmente TF_VAR_db_username e TF_VAR_db_password)
    username = os.getenv("TF_VAR_db_username") or os.getenv("USERNAME")
    password = os.getenv("TF_VAR_db_password") or os.getenv("PASSWORD")
    
    if not host or not username or not password:
        sys.exit("X Credenciais incompletas. Certifique-se que o terraform output contém 'rds_endpoint' e as variaveis TF_VAR_db_username/password estão no .env.")

    return {
        "host": host,
        "port": int(port),
        "username": username,
        "password": password
    }


def connect(creds: dict, database: str | None = None):
    params = dict(
        host=creds["host"],
        port=creds["port"],
        user=creds["username"],
        password=creds["password"],
        connection_timeout=10,
    )
    if database:
        params["database"] = database

    last_exc = None
    for attempt in range(1, CONNECT_RETRIES + 1):
        try:
            return mysql.connector.connect(**params)
        except mysql.connector.Error as exc:
            last_exc = exc
            if attempt < CONNECT_RETRIES:
                print(f"  ! Tentativa {attempt}/{CONNECT_RETRIES} falhou: {exc}\n    Aguardando {CONNECT_DELAY_S}s...")
                time.sleep(CONNECT_DELAY_S)

    raise RuntimeError(f"Não foi possível conectar após {CONNECT_RETRIES} tentativas: {last_exc}")


def split_statements(sql_text: str) -> list[str]:
    """Divide o dump em statements individuais."""
    statements = []
    current = []
    delimiter = ";"

    for line in sql_text.splitlines():
        stripped = line.strip()

        if stripped.startswith("--") or stripped.startswith("#"):
            continue

        if stripped.upper().startswith("DELIMITER"):
            parts = stripped.split()
            delimiter = parts[1] if len(parts) > 1 else ";"
            continue

        current.append(line)

        if stripped.endswith(delimiter):
            stmt = "\n".join(current).strip()
            if delimiter != ";":
                stmt = stmt[: -len(delimiter)]
            if stmt:
                statements.append(stmt)
            current = []

    remaining = "\n".join(current).strip()
    if remaining:
        statements.append(remaining)

    return statements


# --- Etapas principais ------------------------

def step_create_database(creds: dict) -> None:
    print("\n[1/3] Criando banco de dados (se não existir)...")
    conn = None
    try:
        conn = connect(creds)
        cur = conn.cursor()
        cur.execute(f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}` CHARACTER SET utf8mb4;")
        conn.commit()
        cur.close()
        print(f"  OK Banco '{DB_NAME}' pronto.")
    except Exception:
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            conn.close()


def step_load_sql(creds: dict, sql_file: str) -> None:
    print(f"\n[2/3] Carregando dados do arquivo '{sql_file}'...")

    with open(sql_file, encoding="utf-8", errors="replace") as f:
        sql_text = f.read()

    statements = split_statements(sql_text)
    total = len(statements)
    print(f"  {total} statements encontrados.")

    conn = None
    cur = None
    try:
        conn = connect(creds, database=DB_NAME)
        conn.autocommit = False   # transação explícita
        cur = conn.cursor()

        errors = 0
        for i, stmt in enumerate(statements, 1):
            try:
                cur.execute(stmt)
                if cur.with_rows:
                    cur.fetchall()
            except mysql.connector.Error as e:
                errors += 1
                if errors <= 5:
                    print(f"  !  Stmt {i}: {e}")

            if i % max(1, total // 10) == 0:
                pct = int(i / total * 100)
                print(f"  ... {pct}% ({i}/{total})")

        conn.commit()

        if errors:
            print(f"  !  {errors} statement(s) com erro (verifique acima).")
        else:
            print("  OK Todos os statements executados sem erros.")

    except Exception as exc:
        if conn:
            conn.rollback()
        raise RuntimeError(f"Falha na carga de dados - rollback executado: {exc}") from exc
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


def step_quick_check(creds: dict) -> None:
    print(f"\n[3/3] Verificação rápida das tabelas...")
    conn = None
    try:
        conn = connect(creds, database=DB_NAME)
        cur = conn.cursor()
        cur.execute("SHOW TABLES;")
        tables = [row[0] for row in cur.fetchall()]
        cur.close()

        if tables:
            print(f"  OK {len(tables)} tabela(s) encontrada(s): {', '.join(tables)}")
        else:
            print("  X Nenhuma tabela encontrada - verifique o arquivo SQL.")
    finally:
        if conn:
            conn.close()


def main():
    print("=" * 55)
    print("  Carga de Dados - classicmodels lab")
    print("=" * 55)

    sql_file = LOCAL_SQL
    creds = get_credentials()
    print(f"\n  Host: {creds['host']}:{creds['port']}")

    if not os.path.exists(sql_file):
        sys.exit(f"X Arquivo SQL não encontrado: {sql_file}")

    step_create_database(creds)
    step_load_sql(creds, sql_file)
    step_quick_check(creds)

    print("\n" + "=" * 55)
    print("  Carga concluída!")
    print("=" * 55)


if __name__ == "__main__":
    main()
