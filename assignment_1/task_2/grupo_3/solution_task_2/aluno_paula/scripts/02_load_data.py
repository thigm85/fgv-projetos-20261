import os
import sys
import time
from pathlib import Path

import mysql.connector

"""Script 02: carga robusta com transacao, retries e logs por etapa."""


def env_any(names, default=None, required=False):
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    if required and default is None:
        raise RuntimeError(f"Variavel obrigatoria ausente: {', '.join(names)}")
    return default


def log(step: str, msg: str) -> None:
    print(f"[{step}] {msg}")


def split_host_port(raw_host: str, raw_port: str):
    # Aceita DB_HOST com ou sem sufixo ":porta".
    host = raw_host.strip()
    port = int(raw_port)
    if ":" in host:
        maybe_host, maybe_port = host.rsplit(":", 1)
        if maybe_port.isdigit():
            host = maybe_host
            port = int(maybe_port)
    return host, port


def connect_with_retry(host, port, user, password, database, retries, delay_seconds):
    # Retry simples para absorver instabilidades logo após provisionamento.
    for attempt in range(1, retries + 1):
        try:
            return mysql.connector.connect(
                host=host,
                port=port,
                user=user,
                password=password,
                database=database,
                autocommit=False,
                use_pure=True,
            )
        except mysql.connector.Error as exc:
            if attempt == retries:
                raise
            log("retry", f"Falha de conexao ({attempt}/{retries}): {exc}. Tentando novamente em {delay_seconds}s.")
            time.sleep(delay_seconds)

try:
    host = env_any(["DB_HOST"], required=True)
    user = env_any(["DB_USER", "DB_USERNAME"], required=True)
    password = env_any(["DB_PASSWORD"], required=True)
except RuntimeError as exc:
    print(f"[ERRO] {exc}")
    sys.exit(1)

database = env_any(["DB_NAME"], default="classicmodels")
port = env_any(["DB_PORT"], default="3306")
connect_retries = int(env_any(["MYSQL_CONNECT_RETRIES"], default="10"))
connect_delay_seconds = int(env_any(["MYSQL_CONNECT_DELAY_SECONDS"], default="8"))
dry_run = env_any(["DRY_RUN"], default="0") == "1"
host, port = split_host_port(host, port)

# Resolve SQL path with fallback.
base_dir = Path(__file__).resolve()
candidate_paths = [
    base_dir.parents[5] / "task_1" / "data" / "mysqlsampledatabase.sql",
    base_dir.parents[3] / "data" / "mysqlsampledatabase.sql",
]
sql_path = next((p for p in candidate_paths if p.exists()), candidate_paths[0])

if not sql_path.exists():
    print(f"[ERRO] Arquivo SQL nao encontrado em: {sql_path}")
    sys.exit(1)

log("1/5", f"Lendo SQL de: {sql_path}")
sql_commands = sql_path.read_text(encoding="utf-8")
if dry_run:
    log("2/5", "DRY_RUN=1 ativo; carga nao sera executada.")
    sys.exit(0)

log("2/5", f"Conectando ao banco {database} em {host}:{port} com retry ({connect_retries} tentativas).")
conn = connect_with_retry(host, port, user, password, database, connect_retries, connect_delay_seconds)
cursor = conn.cursor()

executed = 0
try:
    # Executa multi-statements em uma transação única.
    log("3/5", "Executando script SQL em transacao.")
    for result in cursor.execute(sql_commands, multi=True):
        _ = result.fetchall() if result.with_rows else None
        executed += 1
except Exception as exc:
    log("ERRO", "Falha durante execucao; aplicando rollback.")
    conn.rollback()
    failed_statement = getattr(cursor, "statement", "<nao disponivel>")
    print(f"Comando (inicio): {str(failed_statement)[:120]}...")
    print(f"Detalhe: {exc}")
    cursor.close()
    conn.close()
    sys.exit(1)

log("4/5", "Commit da transacao.")
conn.commit()
cursor.close()
conn.close()

log("5/5", f"Dados carregados com sucesso. Comandos executados: {executed}")
