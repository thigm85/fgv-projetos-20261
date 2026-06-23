import pymysql
from pymysql.constants import CLIENT
import os

HOST = "classicmodels-rds-lab.chihawye3zpo.us-east-1.rds.amazonaws.com" 

USER = "admin"

PASSWORD = "password" 

print(f"Conectando ao banco de dados em {HOST}...")

try:
    # Conecta ao servidor MySQL usando a flag MULTI_STATEMENTS 
    # (necessário para rodar um arquivo .sql inteiro de uma vez)
    conexao = pymysql.connect(
        host=HOST,
        user=USER,
        password=PASSWORD,
        client_flag=CLIENT.MULTI_STATEMENTS
    )

    with conexao.cursor() as cursor:
        caminho_sql = "../data/mysqlsampledatabase.sql"
        print(f"Lendo o arquivo {caminho_sql}...")
        
        with open(caminho_sql, 'r', encoding='utf-8') as arquivo:
            script_sql = arquivo.read()
            
        print("Executando o script SQL para criar e popular as tabelas. Isso pode levar alguns segundos...")
        cursor.execute(script_sql)
        conexao.commit()
        print("Sucesso! Banco de dados populado com perfeição.")
        
except Exception as e:
    print(f"Ocorreu um erro: {e}")
finally:
    if 'conexao' in locals() and conexao.open:
        conexao.close()