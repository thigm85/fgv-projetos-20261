import pymysql
import sys
import os

# Pra conseguir importar a config
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from config import CFG

def upload_data():
    try:
        conn = pymysql.connect(
            host=CFG.DB_HOST, user=CFG.DB_USER, password=CFG.DB_PASS, autocommit=True
        )
        cursor = conn.cursor()

        # Cria a database
        print(f"Criando database {CFG.DB_NAME}")
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {CFG.DB_NAME};")
        cursor.execute(f"USE {CFG.DB_NAME};")

        print("Carregando dados...")
        with open(CFG.SQL_PATH, 'r', encoding='utf-8') as f:
            full_sql = f.read()
            queries = full_sql.split(';\n') # usa ';' como split
            
        for query in queries:
            if query.strip():
                cursor.execute(query)
        
        print("Dados carregados.")
    except Exception as e:
        print(f"Erro na hora de carregar os dados: {e}")
    finally:
        if 'conn' in locals(): conn.close()

if __name__ == "__main__":
    upload_data()