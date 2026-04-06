import os
from dotenv import load_dotenv
import mysql.connector

load_dotenv()

DB_HOST = os.getenv('DB_HOST')
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')
DB_NAME = os.getenv('DB_NAME')

from pathlib import Path

# Caminho para o arquivo SQL
SQL_FILE_PATH = Path(__file__).resolve().parent.parent.parent / "assignment_1" / "task_1" / "data" / "mysqlsampledatabase.sql"


def load_data():
    try:
        connection = mysql.connector.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD
        )

        cursor = connection.cursor()
        print("Conectado ao MySQL")

        with open(SQL_FILE_PATH, 'r', encoding='utf-8') as file:
            sql_script = file.read()

        print("Executando script...")

        command = ""
        for line in sql_script.splitlines():
            line = line.strip()

            # ignorar linhas vazias
            if not line or line.startswith('--'):
                continue

            command += line + " "

            # final de comando
            if line.endswith(';'):
                try:
                    cursor.execute(command)
                except Exception as e:
                    print(f"Erro ao executar comando: {e}")
                command = ""

        connection.commit()
        print("Banco criado e populado")

    except Exception as e:
        print(f"Erro geral: {e}")

    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'connection' in locals() and connection.is_connected():
            connection.close()


if __name__ == "__main__":
    load_data()