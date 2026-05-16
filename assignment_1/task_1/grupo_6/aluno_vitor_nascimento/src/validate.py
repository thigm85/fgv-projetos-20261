import os

import mysql.connector
from dotenv import load_dotenv

load_dotenv()

DB_HOST = os.getenv("DB_HOST")
DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASS")
DB_NAME = os.getenv("DB_NAME")

def load_data():
    print("Conectando ao banco de dados RDS")
    try:
        conn = mysql.connector.connect(
            host     = DB_HOST,
            user     = DB_USER,
            password = DB_PASS,
            database = DB_NAME,
            use_pure = True,
        )
        cursor = conn.cursor()

        cursor.execute("SHOW TABLES;")
        tables = cursor.fetchall()

        print(f"Total de tabelas: {len(tables)}\n")
        
        for table_tuple in tables:
            table_name = table_tuple[0]
            cursor.execute(f"SELECT COUNT(*) FROM {table_name};")
            count = cursor.fetchone()[0]
            print(f"Tabela \"{table_name}\": {count} registros")

    except Exception as e:
        print(f"Erro na validação: {e}")
    finally:
        if "conn" in locals() and conn.is_connected():
            cursor.close()
            conn.close()

if __name__ == "__main__":
    load_data()