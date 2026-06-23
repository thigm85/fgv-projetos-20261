import os
from pathlib import Path
import pymysql
from pymysql.constants import CLIENT
from dotenv import load_dotenv

load_dotenv()

DB_HOST = os.getenv('DB_HOST')
DB_NAME = os.getenv('DB_NAME')
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')

SQL_PATH = Path(__file__).resolve().parent / '../../data/mysqlsampledatabase.sql'

conexao = pymysql.connect(
    host=DB_HOST,
    user=DB_USER,
    password=DB_PASSWORD,
    client_flag=CLIENT.MULTI_STATEMENTS
)
cursor = conexao.cursor()

cursor.execute(f"create database if not exists {DB_NAME}")
cursor.execute(f"use {DB_NAME}")

with open(SQL_PATH, 'r', encoding='utf-8') as arquivo:
    sql = arquivo.read()

cursor.execute(sql)

conexao.commit()
conexao.close()
print('Banco de dados criado')
