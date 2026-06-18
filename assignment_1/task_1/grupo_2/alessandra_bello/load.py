#!/usr/bin/env python3
import os
import sys
import time
import urllib.request
import zipfile
import re
import pymysql
import pymysql.cursors

def info(msg):  print(f"[INFO] {msg}")
def warn(msg):  print(f"[AVISO] {msg}")
def error(msg): print(f"[ERRO] {msg}"); raise SystemExit(1)
def step(msg):  print(f"[PASSO] {msg}")

def load_env(filepath: str = "rds_connection.env") -> dict:
    env = {}
    if os.path.isfile(filepath):
        with open(filepath) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, val = line.partition("=")
                    env[key.strip()] = val.strip()
        info(f"Variáveis carregadas de {filepath}")
    else:
        warn(f"{filepath} não encontrado. Usando variáveis de ambiente ou padrões.")

    return {
        "host":     env.get("RDS_HOST",     os.environ.get("RDS_HOST",     "ENDPOINT")),
        "port":     int(env.get("RDS_PORT", os.environ.get("RDS_PORT",     "3306"))),
        "db":       env.get("RDS_DB",       os.environ.get("RDS_DB",       "classicmodels")),
        "user":     env.get("RDS_USER",     os.environ.get("RDS_USER",     "admin")),
        "password": env.get("RDS_PASSWORD", os.environ.get("RDS_PASSWORD", "")),
    }

def get_connection(cfg: dict, db: str | None = None) -> pymysql.Connection:
    kwargs = dict(
        host            = cfg["host"],
        port            = cfg["port"],
        user            = cfg["user"],
        password        = cfg["password"],
        connect_timeout = 15,
        charset         = "utf8mb4",
        autocommit      = True,
    )
    if db:
        kwargs["database"] = db
    return pymysql.connect(**kwargs)

def execute_sql_file(conn: pymysql.Connection, sql_path: str):
    with open(sql_path, "r", encoding="utf-8", errors="replace") as f:
        raw = f.read()

    raw = re.sub(r"/\*.*?\*/", "", raw, flags=re.DOTALL)

    statements = []
    current = []
    for line in raw.splitlines():
        stripped = line.strip()
        if stripped.startswith("--") or stripped.startswith("#"):
            continue
        current.append(line)
        if stripped.endswith(";"):
            stmt = "\n".join(current).strip().rstrip(";").strip()
            if stmt:
                statements.append(stmt)
            current = []

    total = len(statements)
    info(f"Executando {total} statements...")

    with conn.cursor() as cur:
        cur.execute("SET FOREIGN_KEY_CHECKS = 0")
        for i, stmt in enumerate(statements, 1):
            try:
                cur.execute(stmt)
                if i == total:
                    info(f"{i}/{total} statements executados")
            except pymysql.err.Error as e:
                if e.args[0] in (1007, 1050, 1060, 1061, 1062):
                    continue
                warn(f"\nStatement {i} falhou ({e.args[0]}): {str(e.args[1])[:120]}")

def print_summary(conn: pymysql.Connection, db: str):
    with conn.cursor() as cur:
        cur.execute(f"""
            SELECT TABLE_NAME,
                   TABLE_ROWS,
                   ROUND(DATA_LENGTH/1024, 1) AS tamanho_kb
            FROM information_schema.TABLES
            WHERE TABLE_SCHEMA = %s
            ORDER BY TABLE_NAME
        """, (db,))
        rows = cur.fetchall()

    header = f"{'Tabela':<20} {'Linhas (aprox)':<18} {'Tamanho (KB)'}"
    sep    = "─" * 52
    print(f"  {header}")
    print(f"  {sep}")
    for table, lines, kb in rows:
        print(f"  {table:<20} {str(lines):<18} {kb}")
    print()

def main():
    print(f"Carregando dados de classicmodels")

    step("Carregando variáveis...")
    cfg = load_env()

    sql_file = sys.argv[1] if len(sys.argv) > 1 else "projetos_2026/mysqlsampledatabase.sql"
    info(f"Arquivo SQL: {sql_file}")

    step("Testando conexão com o RDS...")
    try:
        conn_test = get_connection(cfg)
        conn_test.close()
        info("Conexão estabelecida com sucesso")
    except pymysql.err.OperationalError as e:
        error(
            f"Não foi possível conectar ao RDS: {e}\n"
        )

    step(f"Criando banco de dados '{cfg['db']}'...")
    conn = get_connection(cfg)
    with conn.cursor() as cur:
        cur.execute(
            f"CREATE DATABASE IF NOT EXISTS `{cfg['db']}` "
            "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
        )
    conn.close()
    info(f"Banco '{cfg['db']}' pronto")

    step(f"Carregando dados...")
    conn = get_connection(cfg, db=cfg["db"])
    execute_sql_file(conn, sql_file)
    info("Dados carregados com sucesso")

    step("Resumo pós-carga:")
    print_summary(conn, cfg["db"])
    conn.close()

    print(f"Carga de dados finalizada com sucesso")

if __name__ == "__main__":
    main()