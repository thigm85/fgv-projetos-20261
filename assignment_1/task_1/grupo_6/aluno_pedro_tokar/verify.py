import mysql.connector
from mysql.connector import errorcode

import os

config = {
    "user": "admin_user",
    "password": "ihateavroformat69",
    "host": os.environ.get("DATABASEHOST"),
    "database": "classicmodels",
    "raise_on_warnings": True,
    "ssl_ca": "./global-bundle.pem",
    "ssl_verify_cert": True,
    "use_pure": True
}

expected_tables = [
    "customers", "products", "productlines", "orders", 
    "orderdetails", "payments", "employees", "offices"
]

try:
    print("Conectando na base de dados para validação...")
    with mysql.connector.connect(**config) as conn:
        with conn.cursor() as cursor:
            cursor.execute("SHOW TABLES")
            existing_tables = [table[0] for table in cursor.fetchall()]
            
            print("Verificando existência das tabelas")
            todas_existem = True
            for table in expected_tables:
                if table in existing_tables:
                    print(f"Tabela '{table}' encontrada.")
                else:
                    print(f"Tabela '{table}' NÃO encontrada.")
                    todas_existem = False
            
            if not todas_existem:
                print("Validação falhoU! Nem todas as tabelas foram criadas corretamente.")
            else:
                print("\nVerificando se tabelas tem entradas")
                for table in expected_tables:
                    cursor.execute(f"SELECT COUNT(*) FROM {table}")
                    contagem = cursor.fetchone()[0]
                    
                    if contagem > 0:
                        print(f"Tabela '{table}' populada com {contagem} registos.")
                    else:
                        print(f"Tabela '{table}' está vazia.")

            print("\nValidação concluída com sucesso.")

except mysql.connector.Error as err:
    if err.errno == errorcode.ER_ACCESS_DENIED_ERROR:
        print("Usuário ou senha incorretos.")
    elif err.errno == errorcode.ER_BAD_DB_ERROR:
        print("Banco de dados não existe.")
    else:
        print(f"Erro ao executar SQL: {err}")
