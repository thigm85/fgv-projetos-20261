from dotenv import load_dotenv
load_dotenv()

import mysql.connector
import sys
import os


DB_HOST = os.getenv('DB_HOST')
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')
DB_NAME = 'classicmodels'

def validate_data():
    try:
        print(f"Conectando ao banco '{DB_NAME}' em {DB_HOST}...")
        connection = mysql.connector.connect(
            host=DB_HOST,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD
        )

        if connection.is_connected():
            cursor = connection.cursor()

            cursor.execute("SHOW TABLES;")
            tables = cursor.fetchall()
            
            if not tables:
                print("Nenhuma tabela encontrada. O script de carga pode ter falhado.")
                sys.exit(1)

            
            total_records = 0
            for (table_name,) in tables:
                cursor.execute(f"SELECT COUNT(*) FROM {table_name};")
                count = cursor.fetchone()[0]
                total_records += count
                print(f"Tabela '{table_name}': {count} registros")
            
            print(f"Total de tabelas verificadas: {len(tables)}")
            print(f"Total de registros inseridos: {total_records}")


    except Exception as e:
        print(f"Ocorreu um erro: {e}")
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'connection' in locals() and connection.is_connected():
            connection.close()

if __name__ == "__main__":
    validate_data()