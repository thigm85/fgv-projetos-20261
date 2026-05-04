import os
import sys
import mysql.connector
from dotenv import load_dotenv

load_dotenv()

# 1. Configurações de Conexão
# Substitir o "host" pelo endpoint gerado no outputs do Terraform
DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "database": os.getenv("DB_NAME", "classicmodels"),
    "port": int(os.getenv("DB_PORT", 3306)),
    "use_pure": True
}

SQL_FILE = ".\data\mysqlsampledatabase.sql"

def load_data():
    print("Iniciando conexão com o Amazon RDS...")
    try:
        # Estabelece a conexão
        conn = mysql.connector.connect(**DB_CONFIG)
        conn.autocommit = False
        cursor = conn.cursor()
        print("Conexão estabelecida com sucesso!")

        # Lê o arquivo SQL
        print(f"Lendo o arquivo {SQL_FILE}...")
        with open(SQL_FILE, "r", encoding="utf-8") as file:
            sql_script = file.read()

        # Executa os comandos do arquivo
        print("Executando comandos SQL. Isso pode levar alguns segundos...")
        
        results = cursor.execute(sql_script, multi=True)
        
        # Verifica se 'results' não é None antes de tentar iterar
        if results is not None:
            for _ in results:
                pass
            
        conn.commit()
        print("Carga de dados concluída com sucesso!")
        sys.exit(0)

    except mysql.connector.Error as err:
        print(f"Erro no banco de dados: {err}")
        sys.exit(1)
    except FileNotFoundError:
        print(f"Erro: O arquivo \"{SQL_FILE}\" não foi encontrado no diretório atual.")
        sys.exit(1)
    finally:
        if "conn" in locals() and conn.is_connected():
            cursor.close()
            conn.close()
            print("Conexão encerrada.")

if __name__ == "__main__":
    load_data()