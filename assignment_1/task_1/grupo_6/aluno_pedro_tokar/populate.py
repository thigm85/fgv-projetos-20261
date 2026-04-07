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

try:
    with mysql.connector.connect(**config) as conn:
        with conn.cursor() as cursor:
            with open("data/mysqlsampledatabase.sql", "r", encoding = "utf-8") as f:
                sql_file = f.read()
                
            print("Executando script SQL. Isso pode levar alguns segundos...")
            cursor.execute(sql_file)
            conn.commit()
            print("Arquivo executado com sucesso. O banco agora foi populado.")


except mysql.connector.Error as err:
    if err.errno == errorcode.ER_ACCESS_DENIED_ERROR:
        print("Usuário ou senha incorretos.")
    elif err.errno == errorcode.ER_BAD_DB_ERROR:
        print("Banco de dados não existe.")
    else:
        print(f"Erro ao executar SQL: {err}")
except FileNotFoundError:
    print("Erro: O arquivo .sql não foi encontrado.")
