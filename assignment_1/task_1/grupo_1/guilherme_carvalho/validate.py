import pymysql

conexao = pymysql.connect(
    host='db-classicmodels.cxttwhozt6l7.us-east-1.rds.amazonaws.com',
    user='admin',
    password='senhatop123',
    database='classicmodels'
)
cursor = conexao.cursor()

cursor.execute("select table_name from information_schema.tables where table_schema = 'classicmodels'")
tabelas = cursor.fetchall()

for tabela in tabelas:
    nome_tabela = tabela[0]
    cursor.execute(f"select count(*) from {nome_tabela}")
    qtd = cursor.fetchone()[0]
    print(f"Tabela: {nome_tabela} | Total de Registros: {qtd}")

conexao.close()
