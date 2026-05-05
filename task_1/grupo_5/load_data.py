from dotenv import load_dotenv
load_dotenv()

import mysql.connector
import sys
import os
from pathlib import Path

DB_HOST = os.getenv('DB_HOST')
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')
SQL_FILE_PATH = Path(__file__).resolve().parent.parent.parent / 'data' / 'mysqlsampledatabase.sql'

def load_data():
    try:
        connection = mysql.connector.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            use_pure=True,
        )

        if connection.is_connected():
            print("Conexão bem-sucedida")
            
            with open(SQL_FILE_PATH, 'r', encoding='utf-8') as file:
                sql_script = file.read()

            cursor = connection.cursor()
            print("Executando o script SQL (isso pode levar alguns segundos)...")
            
            cursor.execute(sql_script)
            while cursor.nextset():
                pass

            connection.commit()
            print("Banco de dados 'classicmodels' criado e populado com sucesso!")

    except Exception as e:
        print(f"Ocorreu um erro: {e}")
        sys.exit(1)

    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'connection' in locals() and connection.is_connected():
            connection.close()

if __name__ == "__main__":
    load_data()