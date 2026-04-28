import os
import pymysql
from dotenv import load_dotenv

load_dotenv()

DB_HOST = os.getenv('DB_HOST')
DB_NAME = os.getenv('DB_NAME')
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')

conexao = pymysql.connect(
    host=DB_HOST,
    user=DB_USER,
    password=DB_PASSWORD,
    database=DB_NAME
)
cursor = conexao.cursor()

cursor.execute(f"select table_name from information_schema.tables where table_schema = '{DB_NAME}'")
tabelas = cursor.fetchall()

for tabela in tabelas:
    nome_tabela = tabela[0]
    cursor.execute(f"select count(*) from `{nome_tabela}`")
    qtd = cursor.fetchone()[0]
    print(f"Tabela: {nome_tabela} | Total de Registros: {qtd}")

conexao.close()
