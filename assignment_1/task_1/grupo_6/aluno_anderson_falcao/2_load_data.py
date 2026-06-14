"""
Cria o banco classicmodels e carrega o arquivo SQL de exemplo
"""

import json
import sys
import os
import time
import mysql.connector
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------
# CONFIGURAÇÕES
# ---------------------------------------------
CREDENTIALS_FILE = "rds_credentials.json"
DB_NAME = "classicmodels"
LOCAL_SQL = os.getenv("SQL_FILE", "../../data/mysqlsampledatabase.sql")

# parâmetros de retry de conexão
CONNECT_RETRIES = 5
CONNECT_DELAY_S = 10   # segundos entre tentativas

# --- Utilitários -----------------------------

def load_credentials(filepath: str) -> dict:
    if not os.path.exists(filepath):
        sys.exit(
            f"X Arquivo '{filepath}' não encontrado.\n"
            "   Execute primeiro:  python 1_provision_rds.py"
        )
    with open(filepath) as f:
        return json.load(f)


def connect(creds: dict, database: str | None = None):
    """
    Retries com delay para lidar com instâncias recém-criadas 
    que ainda não aceitam conexões 
    (estado 'available', mas MySQL ainda inicializando internamente).
    """
    params = dict(
        host=creds["host"],
        port=int(creds["port"]),
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
                print(
                    f"  ! Tentativa {attempt}/{CONNECT_RETRIES} falhou: {exc}\n"
                    f"    Aguardando {CONNECT_DELAY_S}s antes de tentar novamente..."
                )
                time.sleep(CONNECT_DELAY_S)

    raise RuntimeError(
        f"Não foi possível conectar após {CONNECT_RETRIES} tentativas: {last_exc}"
    )


def split_statements(sql_text: str) -> list[str]:
    """Divide o dump em statements individuais respeitando delimitadores."""
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
    """
      - Executa toda a carga em uma única transação com rollback explícito em caso de falha.
      - Fecha conn/cur no bloco finally mesmo se houver exceção.
      - Distingue erros "esperados" (ex.: objetos já existentes) de erros críticos.
    """
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

        # Faz commit somente se nenhum erro crítico interrompeu o fluxo
        conn.commit()

        if errors:
            print(f"  !  {errors} statement(s) com erro (verifique acima).")
        else:
            print("  OK Todos os statements executados sem erros.")

    except Exception as exc:
        # rollback explícito: desfaz tudo se algo crítico falhar
        if conn:
            conn.rollback()
        raise RuntimeError(f"Falha na carga de dados — rollback executado: {exc}") from exc
    finally:
        # fecha recursos sempre, independentemente de sucesso ou falha
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
            print("  X Nenhuma tabela encontrada — verifique o arquivo SQL.")
    finally:
        if conn:
            conn.close()


# --- Entry-point --------------------

def main():
    print("=" * 55)
    print("  Carga de Dados — classicmodels lab")
    print("=" * 55)

    sql_file = LOCAL_SQL
    creds = load_credentials(CREDENTIALS_FILE)
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