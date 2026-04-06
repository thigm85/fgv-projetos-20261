import mysql.connector
import sqlparse
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_HOST = 'classicmodels-db.c2zxcfdeoqyt.us-east-1.rds.amazonaws.com'
DB_USER = os.getenv('aws_user')
DB_PASSWORD = os.getenv('aws_password')
SQL_FILE_PATH = os.path.join(BASE_DIR, "..", "..", "data", "mysqlsampledatabase.sql")


def load_sql_file():
    print("Conectando ao servidor MySQL no RDS...")
    try:
        connection = mysql.connector.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD
        )
        cursor = connection.cursor()

        print("Lendo o arquivo SQL...")
        with open(SQL_FILE_PATH, 'r', encoding='utf-8') as file:
            sql_commands = file.read()

        print("Executando os comandos SQL...")

        statements = sqlparse.split(sql_commands)

        for statement in statements:
            stmt = statement.strip()
            if stmt:
                try:
                    cursor.execute(stmt)
                except Exception as e:
                    print("Erro ao executar comando:", e)
        
        connection.commit()
        print("Dados carregados com sucesso no banco 'classicmodels'!")

    except Exception as e:
        print(f"Erro ao carregar dados: {e}")
    finally:
        if 'connection' in locals() and connection.is_connected():
            cursor.close()
            connection.close()

if __name__ == "__main__":
    load_sql_file()