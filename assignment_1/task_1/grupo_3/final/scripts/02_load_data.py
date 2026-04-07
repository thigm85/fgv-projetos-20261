import os
import sys
from pathlib import Path

import mysql.connector

"""
Script 02: loads mysqlsampledatabase.sql into RDS.
Required env vars: DB_HOST, DB_USER, DB_PASSWORD
"""

host = os.getenv("DB_HOST")
user = os.getenv("DB_USER")
password = os.getenv("DB_PASSWORD")

if not host or not user or not password:
    print("[ERRO] Defina DB_HOST, DB_USER e DB_PASSWORD antes de executar.")
    sys.exit(1)

# Resolves task_1/data/mysqlsampledatabase.sql from this file location.
sql_path = Path(__file__).resolve().parents[3] / "data" / "mysqlsampledatabase.sql"

if not sql_path.exists():
    print(f"[ERRO] Arquivo SQL nao encontrado em: {sql_path}")
    sys.exit(1)

conn = mysql.connector.connect(
    host=host,
    user=user,
    password=password,
    autocommit=False,
    use_pure=True,
)
cursor = conn.cursor()

print(f"Lendo SQL de: {sql_path}")
sql_commands = sql_path.read_text(encoding="utf-8")

executed = 0
try:
    # Execute full SQL script as multi-statement to preserve quoted text safely.
    for result in cursor.execute(sql_commands, multi=True):
        _ = result.fetchall() if result.with_rows else None
        executed += 1
except Exception as e:
    conn.rollback()
    failed_statement = getattr(cursor, "statement", "<nao disponivel>")
    print("[ERRO] Falha ao executar comando SQL.")
    print(f"Comando (inicio): {str(failed_statement)[:120]}...")
    print(f"Detalhe: {e}")
    cursor.close()
    conn.close()
    sys.exit(1)

conn.commit()
cursor.close()
conn.close()

print(f"Dados carregados com sucesso. Comandos executados: {executed}")
