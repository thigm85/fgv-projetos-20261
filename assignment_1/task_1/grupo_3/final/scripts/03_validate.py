import os
import sys

import mysql.connector

"""
Script 03: validates expected classicmodels tables and row counts.
Required env vars: DB_HOST, DB_USER, DB_PASSWORD
"""

host = os.getenv("DB_HOST")
user = os.getenv("DB_USER")
password = os.getenv("DB_PASSWORD")

if not host or not user or not password:
    print("[ERRO] Defina DB_HOST, DB_USER e DB_PASSWORD antes de executar.")
    sys.exit(1)

conn = mysql.connector.connect(host=host, user=user, password=password, database="classicmodels")

cursor = conn.cursor()

cursor.execute("SHOW TABLES;")
tables = sorted([t[0] for t in cursor.fetchall()])

print("Tabelas encontradas:")
for table_name in tables:
    print(f"- {table_name}")

expected_tables = [
    "customers",
    "employees",
    "offices",
    "orderdetails",
    "orders",
    "payments",
    "productlines",
    "products",
]

missing_tables = [table for table in expected_tables if table not in tables]
if missing_tables:
    print(f"[ERRO] Tabelas ausentes: {missing_tables}")
    cursor.close()
    conn.close()
    sys.exit(1)

print("\nContagem de linhas:")
invalid_counts = []
for table in expected_tables:
    cursor.execute(f"SELECT COUNT(*) FROM {table}")
    count = cursor.fetchone()[0]
    print(f"- {table}: {count} linhas")
    if count <= 0:
        invalid_counts.append(table)

cursor.close()
conn.close()

if invalid_counts:
    print(f"[ERRO] Tabelas sem registros: {invalid_counts}")
    sys.exit(1)

print("\nValidacao concluida com sucesso.")
