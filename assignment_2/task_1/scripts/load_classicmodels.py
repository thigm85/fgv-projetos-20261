"""
Carrega o banco classicmodels no RDS recém-provisionado (infra/).

Conecta SEM database (o dump mysqlsampledatabase.sql cria o schema classicmodels)
usando MULTI_STATEMENTS, com retry/backoff. Reusa credenciais via db.load_config().

Localiza o dump automaticamente (1º existente):
  - assignment_2/task_1/data/mysqlsampledatabase.sql   (se você copiou para cá)
  - assignment_1/task_1/data/mysqlsampledatabase.sql   (já versionado no repo)
Ou informe explicitamente com --sql <caminho>.

Uso:
  python load_classicmodels.py
  python load_classicmodels.py --sql C:\caminho\mysqlsampledatabase.sql
"""
import argparse
import sys
import time
from pathlib import Path

import pymysql
import pymysql.constants.CLIENT

from db import load_config, BASE_DIR, MAX_RETRIES, CONNECT_TIMEOUT

# Candidatos de localização do dump (relativos à raiz do repo)
REPO_ROOT = BASE_DIR.parents[2]  # .../fgv-projetos-20261
SQL_CANDIDATES = [
    BASE_DIR.parent / "data" / "mysqlsampledatabase.sql",
    REPO_ROOT / "assignment_1" / "task_1" / "data" / "mysqlsampledatabase.sql",
]


def find_sql(explicit: str | None) -> Path:
    if explicit:
        p = Path(explicit)
        if not p.exists():
            print(f"[ERRO] Dump não encontrado: {p}")
            sys.exit(1)
        return p
    for cand in SQL_CANDIDATES:
        if cand.exists():
            return cand
    print("[ERRO] Dump mysqlsampledatabase.sql não encontrado nos caminhos padrão:")
    for c in SQL_CANDIDATES:
        print(f"       - {c}")
    print("       Informe com --sql <caminho>.")
    sys.exit(1)


def connect_no_db(cfg: dict) -> pymysql.connections.Connection:
    """Conecta sem selecionar database, com MULTI_STATEMENTS (para rodar o dump)."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            print(f"[{attempt}/{MAX_RETRIES}] Conectando a {cfg['host']}:{cfg['port']}...")
            conn = pymysql.connect(
                host=cfg["host"],
                port=cfg["port"],
                user=cfg["user"],
                password=cfg["password"],
                connect_timeout=CONNECT_TIMEOUT,
                client_flag=pymysql.constants.CLIENT.MULTI_STATEMENTS,
            )
            print("  Conexão estabelecida.")
            return conn
        except Exception as exc:
            if attempt == MAX_RETRIES:
                print(f"[ERRO] Falha após {MAX_RETRIES} tentativas: {exc}")
                raise
            wait = 2 ** attempt
            print(f"  Falha: {exc}. Aguardando {wait}s...")
            time.sleep(wait)


def main() -> int:
    parser = argparse.ArgumentParser(description="Carrega classicmodels no RDS.")
    parser.add_argument("--sql", default=None, help="Caminho do mysqlsampledatabase.sql.")
    args = parser.parse_args()

    print("=" * 60)
    print("Carga do banco classicmodels no RDS")
    print("=" * 60)

    sql_path = find_sql(args.sql)
    print(f"Dump: {sql_path} ({sql_path.stat().st_size:,} bytes)")

    cfg = load_config()
    conn = None
    try:
        conn = connect_no_db(cfg)
        sql = sql_path.read_text(encoding="utf-8")
        print(f"Executando SQL ({len(sql):,} bytes)...")
        with conn.cursor() as cur:
            cur.execute(sql)
            result_sets = 0
            while cur.nextset():
                result_sets += 1
        conn.commit()
        print(f"  Carga concluída e commitada ({result_sets} result sets).")
    except Exception as exc:
        if conn:
            conn.rollback()
        print(f"\n[ERRO] {exc} — rollback realizado.")
        return 1
    finally:
        if conn:
            conn.close()
            print("  Conexão encerrada.")

    print("\n" + "=" * 60)
    print("classicmodels carregado com sucesso.")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
