import os
import time
import pymysql
from pymysql.constants import CLIENT
from dotenv import load_dotenv

# Carrega variáveis de ambiente
load_dotenv()

# Define o diretório base do script
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Define a raiz do projeto (subindo dois níveis) para achar o arquivo SQL e .env de conexão
PROJECT_ROOT = os.path.dirname(os.path.dirname(BASE_DIR))

def info(msg):  print(f"[INFO] {msg}")
def warn(msg):  print(f"[AVISO] {msg}")
def error(msg): print(f"[ERRO] {msg}"); raise SystemExit(1)
def step(num, total, msg): print(f"[PASSO {num}/{total}] {msg}")

def resolve_sql_path() -> str:
    """Resolve o caminho do script SQL do sample database.

    Prioridade:
    1) Variável de ambiente SQL_FILE (pode ser relativa ao cwd)
    2) Caminho padrão dentro do projeto
    3) Caminho do dataset em assignment_1/task_1/data/
    """
    sql_from_env = os.getenv("SQL_FILE")
    candidates = []

    if sql_from_env:
        # Permite caminhos relativos ao diretório atual
        candidates.append(os.path.abspath(sql_from_env))

    # Tentativa dentro da raiz calculada do projeto
    candidates.append(os.path.join(PROJECT_ROOT, "data", "mysqlsampledatabase.sql"))

    # Dataset original do curso está em task_1/data no repositório
    candidates.append(
        os.path.normpath(
            os.path.join(BASE_DIR, "..", "..", "..", "task_1", "data", "mysqlsampledatabase.sql")
        )
    )

    for path in candidates:
        if path and os.path.exists(path):
            return path

    # Fallback final (caso o usuário copie o arquivo para o cwd)
    if os.path.exists("mysqlsampledatabase.sql"):
        return os.path.abspath("mysqlsampledatabase.sql")

    searched = "\n".join(f"- {p}" for p in candidates)
    error(
        "Arquivo SQL não encontrado. Defina SQL_FILE no .env ou coloque o arquivo em um dos caminhos esperados. "
        f"Caminhos verificados:\n{searched}"
    )

def load_connection_config(filename: str = "rds_connection.env") -> dict:
    filepath = os.path.join(os.getcwd(), filename)
    env = {}
    if os.path.isfile(filepath):
        with open(filepath) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, val = line.partition("=")
                    env[key.strip()] = val.strip()
    return env

def get_connection_with_retry(cfg, max_retries=5, delay=10):
    for i in range(max_retries):
        try:
            info(f"Tentativa {i+1}/{max_retries} de conexão com o banco...")
            connection = pymysql.connect(
                host = cfg.get("RDS_HOST"),
                port = int(cfg.get("RDS_PORT", 3306)),
                user = cfg.get("RDS_USER"),
                password = cfg.get("RDS_PASSWORD"),
                database = cfg.get("RDS_DB"),
                client_flag = CLIENT.MULTI_STATEMENTS,
                autocommit = False, # Transações explícitas
                connect_timeout = 10
            )
            return connection
        except pymysql.MySQLError as e:
            warn(f"Falha na conexão: {e}. Aguardando {delay}s...")
            time.sleep(delay)
    error("Não foi possível conectar ao banco de dados após várias tentativas.")

def load_data():
    total_steps = 4
    print("=== Iniciando Carga de Dados (Foco em Robustez e Transacionalidade) ===")

    step(1, total_steps, "Carregando configurações de conexão")
    cfg = load_connection_config()
    if not cfg.get("RDS_HOST"):
        error("Configurações de conexão (rds_connection.env) não encontradas.")

    step(2, total_steps, "Estabelecendo conexão com RDS (com Retry)")
    connection = get_connection_with_retry(cfg)

    step(3, total_steps, "Lendo script SQL de carga")
    sql_path = resolve_sql_path()
    
    try:
        with open(sql_path, "r", encoding="utf-8") as f:
            sql_script = f.read()
    except Exception as e:
        connection.close()
        error(f"Erro ao ler arquivo SQL em {sql_path}: {e}")

    step(4, total_steps, "Executando carga de dados em transação")
    try:
        with connection.cursor() as cursor:
            # O cursor.execute com multi_statements no pymysql processa tudo
            cursor.execute(sql_script)
        
        connection.commit()
        info("Carga concluída e transação confirmada (commit).")
    except Exception as e:
        connection.rollback()
        error(f"Erro durante a carga. Transação revertida (rollback). Detalhe: {e}")
    finally:
        connection.close()
        info("Conexão encerrada.")

    print("\n[SUCESSO] Banco de dados populado com sucesso.")

if __name__ == "__main__":
    load_data()