import pymysql
from pymysql.constants import CLIENT

conexao = pymysql.connect(
    host='db-classicmodels.cxttwhozt6l7.us-east-1.rds.amazonaws.com',
    user='admin',
    password='senhatop123',
    client_flag=CLIENT.MULTI_STATEMENTS
)
cursor = conexao.cursor()

cursor.execute("create database if not exists classicmodels")
cursor.execute("use classicmodels")

with open('../../data/mysqlsampledatabase.sql', 'r', encoding='utf-8') as arquivo:
    sql = arquivo.read()

cursor.execute(sql)

conexao.commit()
conexao.close()
print('Banco de dados criado')
