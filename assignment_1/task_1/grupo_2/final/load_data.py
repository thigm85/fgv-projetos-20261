import json
import pymysql
from pymysql.constants import CLIENT
import os

### Carregando as configurações

# Define o diretório base do script (grupo_2/final/)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Define a raiz do projeto (subindo dois níveis)
PROJECT_ROOT = os.path.dirname(os.path.dirname(BASE_DIR))

def load_env(filename: str = "rds_connection.env") -> dict:
    # Procura o .env na raiz do projeto
    filepath = os.path.join(PROJECT_ROOT, filename)
    env = {}
    if os.path.isfile(filepath):
        with open(filepath) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, val = line.partition("=")
                    env[key.strip()] = val.strip()
    return env

cfg = load_env()

# Caminho do arquivo SQL (sempre na pasta data na raiz do projeto)
SQL_FILE_PATH = os.path.join(PROJECT_ROOT, "data", "mysqlsampledatabase.sql")

def load_data():
    print(f"Conectando ao banco em {cfg.get('RDS_HOST')}...")

    try:
        # Iniciando a conexão
        connection = pymysql.connect(
            host = cfg.get("RDS_HOST"),
            port = int(cfg.get("RDS_PORT", 3306)),
            user = cfg.get("RDS_USER"),
            password = cfg.get("RDS_PASSWORD"),
            database = cfg.get("RDS_DB"), # Adicionado para usar o banco correto
            client_flag = CLIENT.MULTI_STATEMENTS,
            autocommit = True,
        )

        print("Conexão bem-sucedida. Lendo o arquivo SQL...")

        with open(SQL_FILE_PATH, "r", encoding = "utf-8") as f:
            sql_script = f.read()

        print("Executando o script SQL...")

        with connection.cursor() as cursor:
            cursor.execute(sql_script)

        print("\nDados carregados com sucesso. Banco populado.")

    except FileNotFoundError:
        print(f"\nErro: O arquivo SQL não foi encontrado no caminho: {SQL_FILE_PATH}.")
    except pymysql.MySQLError as e:
        print(f"\nErro no MySQL:\n{e}")
    except Exception as e:
        print(f"\nOcorreu um erro inesperado:\n{e}")
    finally:
        # Garantindo que a conexão será fechada mesmo se houver erro
        if "connection" in locals() and connection.open:
            connection.close()
            print("Conexão encerrada.")

if __name__ == "__main__":
    load_data()