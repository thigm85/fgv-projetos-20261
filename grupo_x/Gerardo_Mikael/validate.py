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

# Pagamentos negativos
cursor.execute("SELECT COUNT(*) FROM payments WHERE amount < 0;")
negativos = cursor.fetchone()[0]

if negativos > 0:
    erros.append(f"{negativos} pagamentos negativos encontrados")


# Pedidos com cliente inválido

cursor.execute("""
SELECT COUNT(*)
FROM orders o
LEFT JOIN customers c ON o.customerNumber = c.customerNumber
WHERE c.customerNumber IS NULL;
""")
invalidos = cursor.fetchone()[0]

if invalidos > 0:
    erros.append(f"{invalidos} pedidos com cliente inválido")
    
# Resultado

cursor.close()
conn.close()

if erros:
    print("Erros encontrados:")
    for e in erros:
        print("-", e)
else:
    print("Tudo certo")