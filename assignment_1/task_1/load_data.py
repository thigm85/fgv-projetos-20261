import mysql.connector
import os
from dotenv import load_dotenv

load_dotenv()

# Configurações do banco (ajuste conforme o output do provisionamento)
DB_HOST = os.getenv("DB_HOST") 
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
SQL_FILE = os.getenv("SQL_FILE")
DB_NAME = os.getenv("DB_NAME")


def execute_sql_file(filename, connection):
    cursor = connection.cursor()
    print(f"Lendo o arquivo {filename}...")

    with open(filename, 'r', encoding='utf-8') as f:
        sql_content = f.read()

    print("Executando scripts SQL...")

    cursor.execute("SET FOREIGN_KEY_CHECKS=0;")

    # Split on semicolons that are NOT inside single-quoted strings
    statements = []
    current = []
    in_string = False
    escape_next = False

    for char in sql_content:
        if escape_next:
            current.append(char)
            escape_next = False
        elif char == '\\' and in_string:
            current.append(char)
            escape_next = True
        elif char == "'" and not in_string:
            in_string = True
            current.append(char)
        elif char == "'" and in_string:
            in_string = False
            current.append(char)
        elif char == ';' and not in_string:
            stmt = ''.join(current).strip()
            if stmt:
                statements.append(stmt)
            current = []
        else:
            current.append(char)

    # Catch any trailing statement without a final semicolon
    stmt = ''.join(current).strip()
    if stmt:
        statements.append(stmt)

    count = 0
    for stmt in statements:
        try:
            cursor.execute(stmt)
            count += 1
        except mysql.connector.Error as e:
            print(f"Aviso: erro ao executar statement ({e}), continuando...")

    cursor.execute("SET FOREIGN_KEY_CHECKS=1;")
    connection.commit()
    cursor.close()

    print(f"Sucesso! {count} comandos executados.")


if __name__ == "__main__":
    if not DB_HOST:
        print("Erro: DB_HOST não definido no ambiente/.env")
    else:
        try:
            print(f"Conectando ao banco em {DB_HOST}...")
            
            conn = mysql.connector.connect(
                host=DB_HOST,
                user=DB_USER,
                password=DB_PASSWORD,
                database=DB_NAME,
                use_pure=True  # 👈 ESSENCIAL
            )

            execute_sql_file(SQL_FILE, conn)
            conn.close()

        except mysql.connector.Error as err:
            print(f"Falha na conexão: {err}")
