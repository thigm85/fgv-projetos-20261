import os
from dotenv import load_dotenv
import mysql.connector

load_dotenv()

conn = mysql.connector.connect(
    host=os.getenv("DB_HOST"),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
    database=os.getenv("DB_NAME")
)

cursor = conn.cursor()

print("Rodando validações...")

erros = []

# Teste de tabelas vazias
cursor.execute("SELECT COUNT(*) FROM customers;")
total = cursor.fetchone()[0]

if total == 0:
    erros.append("Tabela customers está vazia")
    
# Resultado final

cursor.close()
conn.close()

if erros:
    print("Erros encontrados:")
    for e in erros:
        print("-", e)
else:
    print("Tudo certo")