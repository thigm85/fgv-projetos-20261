import os

import sqlparse
import mysql.connector
from dotenv import load_dotenv

load_dotenv()

DB_HOST  = os.getenv("DB_HOST")
DB_USER  = os.getenv("DB_USER")
DB_PASS  = os.getenv("DB_PASS")

SQL_FILE = os.getenv("SQL_FILE", "../../data/mysqlsampledatabase.sql")

def load_data():
    print("Conectando ao banco de dados RDS")
    try:
        conn = mysql.connector.connect(
            host     = DB_HOST,
            user     = DB_USER,
            password = DB_PASS,
            use_pure = True
        )
        cursor = conn.cursor()

        with open(SQL_FILE, "r", encoding="utf-8") as file:
            sql_script = file.read()

        print("Executando a carga de dados")
        
        sql_commands = sqlparse.split(sql_script)

        for command in sql_commands:
            clean_command = command.strip()
            
            if clean_command:
                cursor.execute(clean_command)
        
        conn.commit()
        
        print("Carga de dados concluída com sucesso!")

    except Exception as e:
        print(f"Erro durante a carga de dados: {e}")
    finally:
        if "conn" in locals() and conn.is_connected():
            cursor.close()
            conn.close()

if __name__ == "__main__":
    load_data()