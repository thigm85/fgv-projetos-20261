import pymysql
import sys
import os

# Pra conseguir importar a config
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from config import CFG

def validate():
    conn = None
    try:
        conn = pymysql.connect(
            host=CFG.DB_HOST,
            user=CFG.DB_USER,
            password=CFG.DB_PASS,
            database=CFG.DB_NAME
        )
        cursor = conn.cursor()
        
        # Mostra as tabelas
        cursor.execute("SHOW TABLES;")
        tables = [row[0] for row in cursor.fetchall()]

        print(f"Informações do Banco: \n")
        for table in tables:
            cursor.execute(f"SELECT COUNT(*) FROM {table};")
            count = cursor.fetchone()[0]
            print(f"Tabela: {table.ljust(20)} - Linhas: {count}")
        
    except Exception as e:
        print(f"Falha na validação: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    validate()